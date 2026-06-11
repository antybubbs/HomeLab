(() => {
  const root = document.querySelector("[data-ssh-session]");
  if (!root) return;

  const output = root.querySelector("[data-ssh-output]");
  const passwordForm = root.querySelector("[data-ssh-password-form]");
  const passwordInput = root.querySelector("[data-ssh-password]");
  let socket = null;
  let connected = false;

  if (!passwordForm || !passwordInput || !output) return;

  const ansiClasses = {
    30: "ansi-black",
    31: "ansi-red",
    32: "ansi-green",
    33: "ansi-yellow",
    34: "ansi-blue",
    35: "ansi-magenta",
    36: "ansi-cyan",
    37: "ansi-white",
    90: "ansi-bright-black",
    91: "ansi-bright-red",
    92: "ansi-bright-green",
    93: "ansi-bright-yellow",
    94: "ansi-bright-blue",
    95: "ansi-bright-magenta",
    96: "ansi-bright-cyan",
    97: "ansi-bright-white",
  };

  const escapeHtml = (text) => text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

  const ansiToHtml = (text) => {
    let current = "";
    let html = "";
    const parts = text.split(/(\x1b\[[0-9;]*m)/g);
    parts.forEach((part) => {
      const match = part.match(/^\x1b\[([0-9;]*)m$/);
      if (!match) {
        const safe = escapeHtml(part).replaceAll("\r\n", "\n").replaceAll("\r", "\n");
        html += current ? `<span class="${current}">${safe}</span>` : safe;
        return;
      }
      const codes = match[1].split(";").filter(Boolean).map(Number);
      if (!codes.length || codes.includes(0)) {
        current = "";
        return;
      }
      const colour = codes.find((code) => ansiClasses[code]);
      if (colour) current = ansiClasses[colour];
    });
    return html;
  };

  const append = (text) => {
    output.innerHTML += ansiToHtml(text);
    output.scrollTop = output.scrollHeight;
  };

  const setConnected = (connected) => {
    root.dataset.connected = connected ? "true" : "false";
    if (connected) output.focus();
  };

  passwordForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (socket && socket.readyState === WebSocket.OPEN) return;

    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${scheme}//${window.location.host}${root.dataset.wsUrl}`;
    output.textContent = "Connecting...\r\n";
    socket = new WebSocket(wsUrl);

    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ password: passwordInput.value }));
      passwordInput.value = "";
      passwordForm.hidden = true;
      connected = true;
      setConnected(true);
    });

    socket.addEventListener("message", (event) => append(event.data));
    socket.addEventListener("close", () => {
      append("\r\nSession closed.\r\n");
      connected = false;
      setConnected(false);
    });
    socket.addEventListener("error", () => append("\r\nSession error.\r\n"));
  });

  output.addEventListener("keydown", (event) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    if (!connected) return;

    const ctrl = event.ctrlKey || event.metaKey;
    let payload = "";
    if (ctrl && event.key.length === 1) {
      payload = String.fromCharCode(event.key.toUpperCase().charCodeAt(0) - 64);
    } else if (event.key === "Enter") {
      payload = "\r";
    } else if (event.key === "Backspace") {
      payload = "\x7f";
    } else if (event.key === "Tab") {
      payload = "\t";
    } else if (event.key === "ArrowUp") {
      payload = "\x1b[A";
    } else if (event.key === "ArrowDown") {
      payload = "\x1b[B";
    } else if (event.key === "ArrowRight") {
      payload = "\x1b[C";
    } else if (event.key === "ArrowLeft") {
      payload = "\x1b[D";
    } else if (event.key.length === 1 && !event.altKey) {
      payload = event.key;
    }

    if (payload) {
      event.preventDefault();
      socket.send(payload);
    }
  });
})();
