(() => {
  const root = document.querySelector("[data-ssh-session]");
  if (!root) return;

  const terminalEl = root.querySelector("[data-ssh-terminal]");
  const passwordForm = root.querySelector("[data-ssh-password-form]");
  const passwordInput = root.querySelector("[data-ssh-password]");
  if (!terminalEl || !passwordForm || !passwordInput || !window.Terminal) return;

  const registerWebLinks = () => {
    if (typeof term.registerLinkProvider !== "function") return;

    const urlPattern = /\bhttps?:\/\/[^\s<>"'`]+/gi;
    const trimUrl = (value) => value.replace(/[),.;:!?]+$/g, "");

    term.registerLinkProvider({
      provideLinks: (line, callback) => {
        const bufferLine = term.buffer && term.buffer.active.getLine(line - 1);
        if (!bufferLine) {
          callback([]);
          return;
        }

        const text = bufferLine.translateToString(true);
        const links = [];
        let match = urlPattern.exec(text);
        while (match) {
          const url = trimUrl(match[0]);
          const start = match.index + 1;
          const end = start + url.length - 1;
          links.push({
            text: url,
            range: {
              start: { x: start, y: line },
              end: { x: end, y: line },
            },
            activate: () => window.open(url, "_blank", "noopener,noreferrer"),
            hover: () => terminalEl.classList.add("is-link-hover"),
            leave: () => terminalEl.classList.remove("is-link-hover"),
            decorations: { pointerCursor: true, underline: true },
          });

          match = urlPattern.exec(text);
        }

        callback(links);
      },
    });
  };

  const term = new window.Terminal({
    allowTransparency: false,
    convertEol: true,
    cursorBlink: true,
    cursorInactiveStyle: "block",
    cursorStyle: "block",
    drawBoldTextInBrightColors: true,
    fontFamily: "Caskaydia Cove Nerd Font Mono, Cascadia Mono, Consolas, ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: 13,
    fontWeight: 600,
    fontWeightBold: 700,
    lineHeight: 1.0,
    letterSpacing: 0,
    scrollback: 10000,
    scrollOnUserInput: true,
    smoothScrollDuration: 0,
    termName: "xterm-256color",
    bellStyle: "none",
    rightClickSelectsWord: false,
    fastScrollModifier: "alt",
    fastScrollSensitivity: 5,
    minimumContrastRatio: 1,
    theme: {
      background: "#0c0d0b",
      foreground: "#fafafa",
      cursor: "#fafafa",
      cursorAccent: "#0c0d0b",
      selectionBackground: "#334155",
      black: "#2e3436",
      red: "#ef4444",
      green: "#22c55e",
      yellow: "#f59e0b",
      blue: "#3b82f6",
      magenta: "#a855f7",
      cyan: "#06b6d4",
      white: "#e5e7eb",
      brightBlack: "#64748b",
      brightRed: "#f87171",
      brightGreen: "#86efac",
      brightYellow: "#facc15",
      brightBlue: "#60a5fa",
      brightMagenta: "#c084fc",
      brightCyan: "#67e8f9",
      brightWhite: "#ffffff",
    },
  });
  const fitAddon = window.FitAddon ? new window.FitAddon.FitAddon() : null;
  if (fitAddon) term.loadAddon(fitAddon);
  term.open(terminalEl);
  registerWebLinks();
  if (fitAddon) fitAddon.fit();

  if (typeof term.attachCustomKeyEventHandler === "function") {
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown") return true;
      const key = event.key.toLowerCase();

      if ((event.ctrlKey || event.metaKey) && key === "c" && term.hasSelection()) {
        const selection = term.getSelection();
        if (selection && navigator.clipboard) {
          navigator.clipboard.writeText(selection);
        }
        term.clearSelection();
        return false;
      }

      if ((event.ctrlKey || event.metaKey) && key === "v" && navigator.clipboard) {
        navigator.clipboard.readText().then((text) => {
          if (text && connected && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(text);
          }
        });
        return false;
      }

      return true;
    });
  }

  let socket = null;
  let connected = false;

  const fit = () => {
    if (!fitAddon) return;
    fitAddon.fit();
    if (connected && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(`\x00resize:${term.cols}:${term.rows}`);
    }
  };

  window.addEventListener("resize", fit);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      window.setTimeout(fit, 50);
      if (connected) term.focus();
    }
  });
  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data && event.data.type === "homelab:remote-tab-active") {
      window.setTimeout(fit, 50);
      if (connected) term.focus();
    }
  });
  terminalEl.addEventListener("click", () => term.focus());
  terminalEl.addEventListener("paste", (event) => {
    const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (!text || !connected || !socket || socket.readyState !== WebSocket.OPEN) return;
    event.preventDefault();
    socket.send(text);
  });

  term.onData((data) => {
    if (!connected || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(data);
  });

  passwordForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (socket && socket.readyState === WebSocket.OPEN) return;

    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${scheme}//${window.location.host}${root.dataset.wsUrl}`;
    term.reset();
    term.write("Connecting...\r\n");
    socket = new WebSocket(wsUrl);

    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ password: passwordInput.value, cols: term.cols, rows: term.rows }));
      passwordInput.value = "";
      passwordForm.hidden = true;
      connected = true;
      fit();
      term.focus();
      term.options.cursorBlink = true;
      term.refresh(0, term.rows - 1);
    });

    socket.addEventListener("message", (event) => term.write(event.data));
    socket.addEventListener("close", () => {
      connected = false;
      term.write("\r\nSession closed.\r\n");
      passwordForm.hidden = false;
    });
    socket.addEventListener("error", () => term.write("\r\nSession error.\r\n"));
  });
})();
