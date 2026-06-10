(function () {
  const container = document.querySelector("[data-monitor-content]");
  if (!container) {
    return;
  }

  let loading = false;

  async function refreshCards() {
    if (loading) {
      return;
    }
    loading = true;
    try {
      const response = await fetch("/network-monitor/cards", {
        headers: { "X-Requested-With": "fetch" },
        cache: "no-store",
      });
      if (response.ok) {
        container.innerHTML = await response.text();
      }
    } finally {
      loading = false;
    }
  }

  container.addEventListener("submit", async (event) => {
    const form = event.target.closest(".monitor-refresh-form");
    if (!form) {
      return;
    }
    event.preventDefault();
    const button = form.querySelector("button");
    if (button) {
      button.disabled = true;
      button.classList.add("spinning");
    }
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        cache: "no-store",
      });
      if (response.ok) {
        await refreshCards();
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.classList.remove("spinning");
      }
    }
  });

  window.setInterval(refreshCards, 30000);
})();
