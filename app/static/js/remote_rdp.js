import Guacamole from "/static/vendor/guacamole/guacamole-common.min.js";

const root = document.querySelector("[data-rdp-session]");
if (root) {
  const form = root.querySelector(".rdp-credential-form");
  const log = root.querySelector("[data-rdp-log]");
  const button = form ? form.querySelector("button") : null;
  const shell = root.querySelector("[data-rdp-shell]");
  const displayTarget = root.querySelector("[data-rdp-display]");
  const placeholder = root.querySelector("[data-rdp-placeholder]");
  const statusPanel = root.querySelector("[data-rdp-status]");
  let client = null;
  let tunnel = null;
  let keyboard = null;
  let displayViewport = null;
  let resizeTimer = null;
  let resizeObserver = null;

  const writeLog = (lines) => {
    if (!log) return;
    const stamp = new Date().toLocaleTimeString();
    log.textContent = lines.map((line) => `[${stamp}] ${line}`).join("\n");
  };

  const setStatus = (title, message) => {
    if (!statusPanel) return;
    statusPanel.replaceChildren();
    const heading = document.createElement("h2");
    const detail = document.createElement("p");
    detail.className = "muted";
    heading.textContent = title;
    detail.textContent = message;
    statusPanel.append(heading, detail);
  };

  const displaySize = () => {
    const rect = shell.getBoundingClientRect();
    const dpi = Math.max(96, Math.min(144, Math.round((window.devicePixelRatio || 1) * 96)));
    return {
      width: Math.max(640, Math.floor(rect.width || 1280)),
      height: Math.max(480, Math.floor(rect.height || 720)),
      dpi,
    };
  };

  const fitDisplay = () => {
    if (!client || !displayTarget || !displayViewport) return;
    const display = client.getDisplay();
    const width = display.getWidth();
    const height = display.getHeight();
    if (!width || !height) return;
    const rect = displayTarget.getBoundingClientRect();
    const scale = Math.min(rect.width / width, rect.height / height);
    const safeScale = Math.max(0.1, Math.min(scale, 1.5));
    display.scale(safeScale);
    displayViewport.style.width = `${Math.ceil(width * safeScale)}px`;
    displayViewport.style.height = `${Math.ceil(height * safeScale)}px`;
  };

  const sendDisplaySize = () => {
    if (!client) return;
    const size = displaySize();
    client.sendSize(size.width, size.height);
    fitDisplay();
  };

  const scheduleResize = () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(sendDisplaySize, 200);
  };

  const stopSession = () => {
    if (keyboard) {
      keyboard.onkeydown = null;
      keyboard.onkeyup = null;
      keyboard = null;
    }
    if (client) {
      client.disconnect();
      client = null;
    }
    displayViewport = null;
    tunnel = null;
  };

  const attachInput = () => {
    const displayEl = client.getDisplay().getElement();
    const mouse = new Guacamole.Mouse(displayEl);
    mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = (state) => {
      shell.focus();
      client.sendMouseState(state, true);
    };
    keyboard = new Guacamole.Keyboard(shell);
    keyboard.onkeydown = (keysym) => {
      client.sendKeyEvent(1, keysym);
      return false;
    };
    keyboard.onkeyup = (keysym) => {
      client.sendKeyEvent(0, keysym);
      return false;
    };
  };

  const connectDisplay = (token) => {
    stopSession();
    displayTarget.replaceChildren();
    placeholder.hidden = true;
    setStatus("Connecting", "Opening browser display tunnel.");
    tunnel = new Guacamole.WebSocketTunnel(root.dataset.tunnelUrl);
    client = new Guacamole.Client(tunnel);
    const displayEl = client.getDisplay().getElement();
    displayViewport = document.createElement("div");
    displayViewport.className = "rdp-display-viewport";
    displayViewport.appendChild(displayEl);
    displayTarget.appendChild(displayViewport);
    attachInput();
    client.onerror = (error) => {
      writeLog([`RDP display error: ${error.message || "Unknown error"}`]);
      setStatus("Connection error", error.message || "The RDP session could not be opened.");
      form.hidden = false;
      button.disabled = false;
    };
    client.onstatechange = (state) => {
      if (state === Guacamole.Client.State.CONNECTED) {
        setStatus("Connected", "RDP session is active.");
        shell.focus();
        fitDisplay();
      }
      if (state === Guacamole.Client.State.DISCONNECTED) {
        setStatus("Disconnected", "The RDP session has ended.");
        form.hidden = false;
        button.disabled = false;
      }
    };
    client.getDisplay().onresize = fitDisplay;
    client.connect(`token=${encodeURIComponent(token)}`);
  };

  window.addEventListener("resize", scheduleResize);
  if (window.ResizeObserver && displayTarget) {
    resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(displayTarget);
  }
  window.addEventListener("beforeunload", stopSession);

  form.addEventListener("submit", (event) => event.preventDefault());
  button.addEventListener("click", async () => {
    button.disabled = true;
    writeLog(["Creating RDP session. Password is not stored."]);
    const formData = new FormData(form);
    const size = displaySize();
    try {
      const response = await fetch(root.dataset.startUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          csrf_token: formData.get("csrf_token"),
          username: formData.get("rdp_username"),
          password: formData.get("rdp_password"),
          width: size.width,
          height: size.height,
          dpi: size.dpi,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
        }),
      });
      const data = await response.json();
      writeLog(data.logs || [`Unexpected response: ${response.status}`]);
      if (!response.ok || !data.ok || !data.token) {
        button.disabled = false;
        return;
      }
      const passwordInput = form.querySelector("input[name='rdp_password']");
      if (passwordInput) passwordInput.value = "";
      form.hidden = true;
      connectDisplay(data.token);
    } catch (error) {
      writeLog([`Browser request failed: ${error}`]);
      button.disabled = false;
    }
  });
}
