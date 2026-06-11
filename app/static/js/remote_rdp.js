(() => {
  const root = document.querySelector("[data-rdp-session]");
  if (!root) return;

  const form = root.querySelector(".rdp-credential-form");
  const log = root.querySelector("[data-rdp-log]");
  const button = form ? form.querySelector("button") : null;
  if (!form || !log || !button) return;

  const writeLog = (lines) => {
    const stamp = new Date().toLocaleTimeString();
    log.textContent = lines.map((line) => `[${stamp}] ${line}`).join("\n");
  };

  form.addEventListener("submit", (event) => event.preventDefault());
  button.addEventListener("click", async () => {
    button.disabled = true;
    writeLog(["Starting checks. Password will be sent for this request only and is not stored."]);
    const formData = new FormData(form);
    try {
      const response = await fetch(root.dataset.checkUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          csrf_token: formData.get("csrf_token"),
          username: formData.get("rdp_username"),
          password: formData.get("rdp_password"),
        }),
      });
      const data = await response.json();
      writeLog(data.logs || [`Unexpected response: ${response.status}`]);
    } catch (error) {
      writeLog([`Browser request failed: ${error}`]);
    } finally {
      button.disabled = false;
    }
  });
})();
