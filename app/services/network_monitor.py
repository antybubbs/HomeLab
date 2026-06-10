import asyncio
import os
import socket
import struct
import time
from datetime import datetime, timedelta
from ipaddress import ip_address

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.models import IPAddress, NetworkMonitor, NetworkMonitorCheck

CHECK_INTERVAL_SECONDS = 10
MAX_CHECK_HISTORY = 1000


def monitor_label(monitor: NetworkMonitor) -> str:
    if monitor.display_name:
        return monitor.display_name
    if monitor.ip_address and monitor.ip_address.name:
        return monitor.ip_address.name
    return monitor.ip_address.address if monitor.ip_address else "Unknown monitor"


def clamp_interval(value: int) -> int:
    return min(max(value, 60), 86400)


def clamp_timeout(value: int) -> int:
    return min(max(value, 500), 10000)


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def ping_ipv4(address: str, timeout_ms: int) -> tuple[bool, int | None, str | None]:
    parsed = ip_address(address)
    if parsed.version != 4:
        return False, None, "IPv6 ping is not supported yet."
    packet_id = os.getpid() & 0xFFFF
    sequence = int(time.monotonic() * 1000) & 0xFFFF
    header = struct.pack("!BBHHH", 8, 0, 0, packet_id, sequence)
    payload = struct.pack("!d", time.monotonic()) + b"HomeLab"
    packet = struct.pack("!BBHHH", 8, 0, checksum(header + payload), packet_id, sequence) + payload
    timeout = timeout_ms / 1000
    started = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (address, 0))
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    return False, None, "Timed out"
                sock.settimeout(remaining)
                response, _ = sock.recvfrom(1024)
                header_length = (response[0] & 0x0F) * 4
                icmp = response[header_length:header_length + 8]
                if len(icmp) < 8:
                    continue
                icmp_type, _, _, response_id, response_sequence = struct.unpack("!BBHHH", icmp)
                if icmp_type == 0 and response_id == packet_id and response_sequence == sequence:
                    latency = int((time.monotonic() - started) * 1000)
                    return True, latency, None
    except PermissionError:
        return False, None, "Ping needs NET_RAW capability in Docker."
    except OSError as exc:
        return False, None, str(exc)


def fallback_due_monitors(db: Session) -> list[NetworkMonitor]:
    now = datetime.utcnow()
    rows = db.query(NetworkMonitor).join(IPAddress).filter(NetworkMonitor.is_enabled == True).limit(250).all()
    return [
        row for row in rows
        if row.last_checked_at is None or row.last_checked_at <= now - timedelta(seconds=clamp_interval(row.interval_seconds))
    ][:25]


def prune_history(db: Session, monitor_id: int) -> None:
    old_rows = db.query(NetworkMonitorCheck.id).filter(
        NetworkMonitorCheck.monitor_id == monitor_id
    ).order_by(NetworkMonitorCheck.checked_at.desc()).offset(MAX_CHECK_HISTORY).all()
    if old_rows:
        old_ids = [row.id for row in old_rows]
        db.query(NetworkMonitorCheck).filter(NetworkMonitorCheck.id.in_(old_ids)).delete(synchronize_session=False)


def run_monitor_check(db: Session, monitor: NetworkMonitor) -> None:
    now = datetime.utcnow()
    ok, latency_ms, error = ping_ipv4(monitor.ip_address.address, clamp_timeout(monitor.timeout_ms))
    status = "up" if ok else "down"
    monitor.last_status = status
    monitor.last_latency_ms = latency_ms
    monitor.last_error = error
    monitor.last_checked_at = now
    db.add(NetworkMonitorCheck(monitor_id=monitor.id, status=status, latency_ms=latency_ms, error=error, checked_at=now))
    prune_history(db, monitor.id)
    db.commit()


def run_monitor_check_by_id(monitor_id: int) -> None:
    db = SessionLocal()
    try:
        monitor = db.get(NetworkMonitor, monitor_id)
        if monitor and monitor.is_enabled and monitor.ip_address:
            try:
                run_monitor_check(db, monitor)
            except Exception as exc:
                now = datetime.utcnow()
                monitor.last_status = "down"
                monitor.last_latency_ms = None
                monitor.last_error = str(exc)
                monitor.last_checked_at = now
                db.add(NetworkMonitorCheck(monitor_id=monitor.id, status="down", latency_ms=None, error=str(exc), checked_at=now))
                db.commit()
    finally:
        db.close()


async def monitor_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            monitor_ids = [monitor.id for monitor in fallback_due_monitors(db)]
        finally:
            db.close()
        for monitor_id in monitor_ids:
            await asyncio.to_thread(run_monitor_check_by_id, monitor_id)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
