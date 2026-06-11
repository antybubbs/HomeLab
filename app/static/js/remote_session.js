(() => {
  const root = document.querySelector("[data-ssh-session]");
  if (!root) return;

  const output = root.querySelector("[data-ssh-output]");
  const passwordForm = root.querySelector("[data-ssh-password-form]");
  const passwordInput = root.querySelector("[data-ssh-password]");
  const commandForm = root.querySelector("[data-ssh-command-form]");
  const commandInput = root.querySelector("[data-ssh-command]");
  const sendButton = commandForm ? commandForm.querySelector("button") : null;
  let socket = null;

  if (!passwordForm || !passwordInput || !commandForm || !commandInput || !output) return;

  const append = (text) => {
    output.textContent += text;
    output.scrollTop = output.scrollHeight;
  };

  const setConnected = (connected) => {
    commandInput.disabled = !connected;
    if (sendButton) sendButton.disabled = !connected;
    if (connected) commandInput.focus();
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
      setConnected(true);
    });

    socket.addEventListener("message", (event) => append(event.data));
    socket.addEventListener("close", () => {
      append("\r\nSession closed.\r\n");
      setConnected(false);
    });
    socket.addEventListener("error", () => append("\r\nSession error.\r\n"));
  });

  commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(`${commandInput.value}\n`);
    commandInput.value = "";
  });
})();
