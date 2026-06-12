import asyncio
import secrets
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette import status

from app.core.csrf import csrf_context, validate_csrf_token
from app.db.session import SessionLocal, get_db
from app.models.models import RemoteAccess, RemoteManagerSetting
from app.routers.auth import require_admin, require_user
from app.services.audit import write_audit

router = APIRouter(prefix="/remote-manager")
templates = Jinja2Templates(directory="app/templates")
PROTOCOLS = {"ssh", "rdp"}
SETTINGS = {
    "guacamole_enabled": "0",
    "guacd_host": "",
    "guacd_port": "4822",
}
RDP_TOKEN_TTL_SECONDS = 60


@dataclass
class RDPSessionToken:
    remote_id: int
    user_id: int
    username: str
    password: str
    width: int
    height: int
    dpi: int
    timezone: str
    created_at: float


rdp_tokens: dict[str, RDPSessionToken] = {}


def remote_label(row: RemoteAccess) -> str:
    if row.display_name:
        return row.display_name
    if row.ip_address and row.ip_address.name:
        return row.ip_address.name
    return row.ip_address.address if row.ip_address else "Remote host"


def clean_protocol(value: str) -> str:
    value = value.lower().strip()
    return value if value in PROTOCOLS else "ssh"


def default_port(protocol: str) -> int:
    return 3389 if protocol == "rdp" else 22


def clean_port(value: int, protocol: str) -> int:
    if 1 <= value <= 65535:
        return value
    return default_port(protocol)


def clean_dimension(value: int, default: int, minimum: int, maximum: int) -> int:
    if minimum <= value <= maximum:
        return value
    return default


def int_payload(payload: dict, key: str, default: int) -> int:
    try:
        return int(payload.get(key) or default)
    except (TypeError, ValueError):
        return default


def fingerprint_for(host_key) -> str:
    return host_key.get_fingerprint("sha256")


def settings_map(db: Session) -> dict[str, str]:
    values = SETTINGS.copy()
    for row in db.query(RemoteManagerSetting).all():
        if row.key in values:
            values[row.key] = row.value or ""
    return values


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(RemoteManagerSetting).filter(RemoteManagerSetting.key == key).first()
    if not row:
        row = RemoteManagerSetting(key=key)
        db.add(row)
    row.value = value


def cleanup_rdp_tokens() -> None:
    now = time.time()
    expired = [token for token, session in rdp_tokens.items() if now - session.created_at > RDP_TOKEN_TTL_SECONDS]
    for token in expired:
        rdp_tokens.pop(token, None)


def guac_element(value: object) -> str:
    text = str(value)
    return f"{len(text)}.{text}"


def guac_instruction(opcode: str, *args: object) -> str:
    return ",".join([guac_element(opcode), *(guac_element(arg) for arg in args)]) + ";"


class GuacParser:
    def __init__(self) -> None:
        self.buffer = ""
        self.elements: list[str] = []
        self.offset = 0
        self.element_end = -1

    def receive(self, data: str) -> list[tuple[str, list[str]]]:
        self.buffer += data
        instructions: list[tuple[str, list[str]]] = []
        while True:
            if self.element_end >= self.offset:
                element = self.buffer[self.offset:self.element_end]
                terminator = self.buffer[self.element_end:self.element_end + 1]
                if not terminator:
                    break
                self.elements.append(element)
                self.offset = self.element_end + 1
                self.element_end = -1
                if terminator == ";":
                    opcode = self.elements[0]
                    instructions.append((opcode, self.elements[1:]))
                    self.elements = []
                elif terminator != ",":
                    raise ValueError("Invalid Guacamole instruction terminator")
            dot = self.buffer.find(".", self.offset)
            if dot == -1:
                break
            raw_length = self.buffer[self.offset:dot]
            if not raw_length.isdigit():
                raise ValueError("Invalid Guacamole element length")
            length = int(raw_length)
            start = dot + 1
            end = start + length
            if len(self.buffer) <= end:
                break
            self.offset = start
            self.element_end = end
        if self.offset > 4096:
            consumed = self.offset
            self.buffer = self.buffer[self.offset:]
            self.offset = 0
            if self.element_end >= 0:
                self.element_end -= consumed
        return instructions


async def read_guac_instruction(reader: asyncio.StreamReader) -> tuple[str, list[str]]:
    parser = GuacParser()
    while True:
        data = await reader.read(1)
        if not data:
            raise ConnectionError("guacd closed the connection during handshake")
        instructions = parser.receive(data.decode("utf-8", errors="strict"))
        if instructions:
            return instructions[0]


def rdp_argument_value(name: str, row: RemoteAccess, session: RDPSessionToken) -> str:
    values = {
        "hostname": row.ip_address.address,
        "port": str(row.port),
        "username": session.username,
        "password": session.password,
        "domain": "",
        "width": str(session.width),
        "height": str(session.height),
        "dpi": str(session.dpi),
        "resize-method": "display-update",
        "security": "any",
        "ignore-cert": "true",
        "enable-wallpaper": "false",
        "enable-theming": "false",
        "enable-font-smoothing": "true",
        "enable-full-window-drag": "false",
        "enable-desktop-composition": "false",
        "disable-audio": "true",
        "server-layout": "en-gb-qwerty",
        "timezone": session.timezone,
    }
    return values.get(name, "")


async def connect_guacd(row: RemoteAccess, settings: dict[str, str], session: RDPSessionToken) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    guacd_host = settings.get("guacd_host", "").strip()
    if not guacd_host or settings.get("guacamole_enabled") != "1":
        raise ConnectionError("Guacamole is not enabled or guacd is not configured")
    try:
        raw_guacd_port = int(settings.get("guacd_port") or 4822)
    except ValueError:
        raw_guacd_port = 4822
    guacd_port = clean_port(raw_guacd_port, "rdp")
    reader, writer = await asyncio.wait_for(asyncio.open_connection(guacd_host, guacd_port), timeout=10)
    try:
        writer.write(guac_instruction("select", "rdp").encode("utf-8"))
        await writer.drain()
        opcode, args = await read_guac_instruction(reader)
        if opcode != "args" or not args:
            raise ConnectionError("guacd did not return RDP connection arguments")
        protocol_version = args[0] if args[0].startswith("VERSION_") else ""
        argument_names = args[1:] if protocol_version else args
        writer.write(guac_instruction("size", session.width, session.height, session.dpi).encode("utf-8"))
        writer.write(guac_instruction("audio").encode("utf-8"))
        writer.write(guac_instruction("video").encode("utf-8"))
        writer.write(guac_instruction("image", "image/png", "image/jpeg", "image/webp").encode("utf-8"))
        if session.timezone:
            writer.write(guac_instruction("timezone", session.timezone).encode("utf-8"))
        writer.write(guac_instruction("name", session.username or "HomeLab").encode("utf-8"))
        connect_args = [rdp_argument_value(name, row, session) for name in argument_names]
        if protocol_version:
            connect_args.insert(0, protocol_version)
        writer.write(guac_instruction("connect", *connect_args).encode("utf-8"))
        await writer.drain()
        return reader, writer
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise


def require_remote_session(db: Session, remote_id: int) -> RemoteAccess:
    row = db.get(RemoteAccess, remote_id)
    if not row or not row.is_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remote access entry not found")
    return row


async def tcp_check(host: str, port: int, timeout: float = 5) -> tuple[bool, str]:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True, "reachable"
    except Exception as exc:
        return False, str(exc)


@router.get("")
def remote_list(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    rows = db.query(RemoteAccess).filter(RemoteAccess.is_enabled == True).order_by(RemoteAccess.protocol.asc(), RemoteAccess.display_name.asc(), RemoteAccess.id.asc()).all()
    return templates.TemplateResponse(request, "remote_manager.html", {"user": user, "rows": rows, "remote_label": remote_label, **csrf_context(request)})


@router.get("/settings")
def remote_settings(request: Request, db: Session = Depends(get_db), user=Depends(require_admin)):
    return templates.TemplateResponse(request, "remote_manager_settings.html", {"user": user, "settings": settings_map(db), "message": None, **csrf_context(request)})


@router.post("/settings")
def save_remote_settings(request: Request, csrf_token: str = Form(...), guacamole_enabled: str = Form(""), guacd_host: str = Form("", max_length=255), guacd_port: int = Form(4822), db: Session = Depends(get_db), user=Depends(require_admin)):
    validate_csrf_token(request, csrf_token)
    set_setting(db, "guacamole_enabled", "1" if guacamole_enabled else "0")
    set_setting(db, "guacd_host", guacd_host.strip())
    set_setting(db, "guacd_port", str(clean_port(guacd_port, "rdp")))
    db.commit()
    write_audit(db, user, "update", "remote_manager_settings", ip_address=request.client.host if request.client else None, detail="Updated Remote Manager settings")
    return templates.TemplateResponse(request, "remote_manager_settings.html", {"user": user, "settings": settings_map(db), "message": "Settings saved.", **csrf_context(request)})


@router.get("/{remote_id}/session")
def remote_session(request: Request, remote_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    row = require_remote_session(db, remote_id)
    rows = db.query(RemoteAccess).filter(RemoteAccess.is_enabled == True).order_by(RemoteAccess.protocol.asc(), RemoteAccess.display_name.asc(), RemoteAccess.id.asc()).all()
    settings = settings_map(db)
    title = remote_label(row)
    return templates.TemplateResponse(request, "remote_session.html", {"user": user, "remote": row, "rows": rows, "remote_label": title, "remote_label_fn": remote_label, "settings": settings, **csrf_context(request)})


@router.post("/{remote_id}/rdp/check")
async def rdp_check(request: Request, remote_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    payload = await request.json()
    validate_csrf_token(request, str(payload.get("csrf_token", "")))
    row = require_remote_session(db, remote_id)
    if row.protocol != "rdp":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Remote entry is not configured for RDP")
    settings = settings_map(db)
    logs = []
    logs.append(f"Starting RDP pre-flight for {row.ip_address.address}:{row.port}.")
    if not payload.get("username"):
        logs.append("No username was provided.")
    if not payload.get("password"):
        logs.append("No password was provided. It is not stored by HomeLab.")
    if settings.get("guacamole_enabled") != "1":
        logs.append("Guacamole is disabled in Remote Manager Settings.")
        return JSONResponse({"ok": False, "logs": logs})
    guacd_host = settings.get("guacd_host", "").strip()
    if not guacd_host:
        logs.append("No guacd host is configured.")
        return JSONResponse({"ok": False, "logs": logs})
    try:
        raw_guacd_port = int(settings.get("guacd_port") or 4822)
    except ValueError:
        raw_guacd_port = 4822
    guacd_port = clean_port(raw_guacd_port, "rdp")
    logs.append(f"Checking guacd at {guacd_host}:{guacd_port}.")
    guacd_ok, guacd_result = await tcp_check(guacd_host, guacd_port)
    logs.append(f"guacd check: {guacd_result}.")
    logs.append(f"Checking target RDP port at {row.ip_address.address}:{row.port}.")
    target_ok, target_result = await tcp_check(row.ip_address.address, row.port)
    logs.append(f"target RDP check: {target_result}.")
    if guacd_ok and target_ok:
        logs.append("Pre-flight checks passed. Browser RDP display transport is the next piece to wire in.")
    else:
        logs.append("Pre-flight checks failed. Fix the failed network check before the browser RDP display can connect.")
    return JSONResponse({"ok": guacd_ok and target_ok, "logs": logs})


@router.post("/{remote_id}/rdp/start")
async def rdp_start(request: Request, remote_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    payload = await request.json()
    validate_csrf_token(request, str(payload.get("csrf_token", "")))
    row = require_remote_session(db, remote_id)
    if row.protocol != "rdp":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Remote entry is not configured for RDP")
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        return JSONResponse({"ok": False, "logs": ["Username and password are required for RDP."]}, status_code=400)
    settings = settings_map(db)
    logs = [f"Preparing RDP session for {row.ip_address.address}:{row.port}."]
    if settings.get("guacamole_enabled") != "1" or not settings.get("guacd_host", "").strip():
        logs.append("Guacamole is not enabled or guacd is not configured.")
        return JSONResponse({"ok": False, "logs": logs}, status_code=400)
    cleanup_rdp_tokens()
    token = secrets.token_urlsafe(32)
    rdp_tokens[token] = RDPSessionToken(
        remote_id=row.id,
        user_id=user.id,
        username=username,
        password=password,
        width=clean_dimension(int_payload(payload, "width", 1280), 1280, 640, 7680),
        height=clean_dimension(int_payload(payload, "height", 720), 720, 480, 4320),
        dpi=clean_dimension(int_payload(payload, "dpi", 96), 96, 72, 240),
        timezone=str(payload.get("timezone", ""))[:80],
        created_at=time.time(),
    )
    logs.append("Session token created. Opening browser display tunnel.")
    return JSONResponse({"ok": True, "token": token, "logs": logs})


@router.websocket("/{remote_id}/ssh/ws")
async def ssh_websocket(websocket: WebSocket, remote_id: int):
    user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
    if not user_id:
        await websocket.close(code=1008)
        return
    db = SessionLocal()
    try:
        remote = db.get(RemoteAccess, remote_id)
        if not remote or not remote.is_enabled or remote.protocol != "ssh" or not remote.username:
            await websocket.close(code=1008)
            return
        host = remote.ip_address.address
        port = remote.port
        username = remote.username
        expected_fingerprint = remote.host_key_fingerprint
    finally:
        db.close()
    await websocket.accept()
    client = None
    try:
        payload = await websocket.receive_json()
        password = payload.get("password", "")
        if not password:
            await websocket.send_text("\r\nPassword is required.\r\n")
            await websocket.close(code=1008)
            return
        try:
            import asyncssh

            client = await asyncio.wait_for(
                asyncssh.connect(host, port=port, username=username, password=password, known_hosts=None),
                timeout=10,
            )
            current_fingerprint = fingerprint_for(client.get_server_host_key())
            if expected_fingerprint and expected_fingerprint != current_fingerprint:
                client.close()
                await client.wait_closed()
                await websocket.send_text("\r\nSSH host key fingerprint has changed. Connection refused.\r\n")
                await websocket.close(code=1011)
                return
            if not expected_fingerprint:
                update_db = SessionLocal()
                try:
                    update_row = update_db.get(RemoteAccess, remote_id)
                    if update_row and not update_row.host_key_fingerprint:
                        update_row.host_key_fingerprint = current_fingerprint
                        update_db.commit()
                finally:
                    update_db.close()
            process = await client.create_process(term_type="xterm-256color", term_size=(160, 48))
        except Exception as exc:
            await websocket.send_text(f"\r\nSSH connection failed: {exc}\r\n")
            await websocket.close(code=1011)
            return

        async def read_loop():
            try:
                while True:
                    data = await process.stdout.read(4096)
                    if not data:
                        break
                    await websocket.send_text(data)
            except Exception:
                pass

        async def write_loop():
            try:
                while True:
                    text = await websocket.receive_text()
                    if text.startswith("\x00resize:"):
                        try:
                            _, cols, rows = text.split(":", 2)
                            process.change_terminal_size(int(cols), int(rows))
                        except Exception:
                            pass
                        continue
                    process.stdin.write(text)
            except WebSocketDisconnect:
                pass

        tasks = {asyncio.create_task(read_loop()), asyncio.create_task(write_loop())}
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if not task.done():
                task.cancel()
    finally:
        if client:
            try:
                client.close()
                await client.wait_closed()
            except Exception:
                pass


@router.websocket("/{remote_id}/rdp/ws")
async def rdp_websocket(websocket: WebSocket, remote_id: int):
    user_id = websocket.session.get("user_id") if hasattr(websocket, "session") else None
    if not user_id:
        await websocket.close(code=1008)
        return
    token = websocket.query_params.get("token", "")
    cleanup_rdp_tokens()
    session = rdp_tokens.pop(token, None)
    if not session or session.user_id != user_id or session.remote_id != remote_id:
        await websocket.close(code=1008)
        return
    db = SessionLocal()
    try:
        remote = db.get(RemoteAccess, remote_id)
        if not remote or not remote.is_enabled or remote.protocol != "rdp":
            await websocket.close(code=1008)
            return
        _ = remote.ip_address.address
        settings = settings_map(db)
    finally:
        db.close()

    await websocket.accept(subprotocol="guacamole")
    guacd_writer = None
    try:
        try:
            guacd_reader, guacd_writer = await connect_guacd(remote, settings, session)
        except Exception as exc:
            await websocket.send_text(guac_instruction("error", f"RDP connection failed: {exc}", 512))
            await websocket.close(code=1011)
            return
        finally:
            session.password = ""

        async def guacd_to_browser():
            try:
                while True:
                    data = await guacd_reader.read(16384)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        async def browser_to_guacd():
            try:
                while True:
                    data = await websocket.receive_text()
                    guacd_writer.write(data.encode("utf-8"))
                    await guacd_writer.drain()
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        tasks = {asyncio.create_task(guacd_to_browser()), asyncio.create_task(browser_to_guacd())}
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if not task.done():
                task.cancel()
    finally:
        if guacd_writer:
            try:
                guacd_writer.close()
                await guacd_writer.wait_closed()
            except Exception:
                pass
