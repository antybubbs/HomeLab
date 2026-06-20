(function () {
  const viewStorageKey = "homelab.runbook.view";
  const viewButtons = Array.from(document.querySelectorAll("[data-runbook-view-button]"));
  const views = Array.from(document.querySelectorAll("[data-runbook-view]"));

  function setRunbookView(view) {
    const nextView = view === "table" ? "table" : "tiles";
    views.forEach((item) => {
      item.hidden = item.dataset.runbookView !== nextView;
    });
    viewButtons.forEach((button) => {
      const active = button.dataset.runbookViewButton === nextView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (views.length) {
      localStorage.setItem(viewStorageKey, nextView);
    }
  }

  if (views.length && viewButtons.length) {
    setRunbookView(localStorage.getItem(viewStorageKey) || "tiles");
    viewButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setRunbookView(button.dataset.runbookViewButton);
      });
    });
  }

  const textarea = document.querySelector("[data-runbook-markdown]");
  const preview = document.querySelector("[data-runbook-preview]");
  if (!textarea || !preview) return;

  const escapeHtml = (value) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const inline = (value) =>
    escapeHtml(value)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');

  function render(markdown) {
    const lines = markdown.replace(/\r\n/g, "\n").split("\n");
    const output = [];
    let paragraph = [];
    let listOpen = false;
    let codeOpen = false;
    let code = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      output.push(`<p>${paragraph.map((line) => inline(line)).join("<br>")}</p>`);
      paragraph = [];
    };

    const closeList = () => {
      if (!listOpen) return;
      output.push("</ul>");
      listOpen = false;
    };

    lines.forEach((line) => {
      const stripped = line.trim();
      if (stripped.startsWith("```")) {
        if (codeOpen) {
          output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
          code = [];
          codeOpen = false;
        } else {
          flushParagraph();
          closeList();
          codeOpen = true;
        }
        return;
      }

      if (codeOpen) {
        code.push(line);
        return;
      }

      if (!stripped) {
        flushParagraph();
        closeList();
        return;
      }

      const heading = stripped.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        closeList();
        const level = heading[1].length + 1;
        output.push(`<h${level}>${inline(heading[2])}</h${level}>`);
        return;
      }

      const bullet = stripped.match(/^[-*]\s+(.+)$/);
      if (bullet) {
        flushParagraph();
        if (!listOpen) {
          output.push("<ul>");
          listOpen = true;
        }
        output.push(`<li>${inline(bullet[1])}</li>`);
        return;
      }

      paragraph.push(stripped);
    });

    if (codeOpen) output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
    flushParagraph();
    closeList();
    return output.join("\n") || '<p class="muted">Preview appears here as you write.</p>';
  }

  const update = () => {
    preview.innerHTML = render(textarea.value);
  };

  textarea.addEventListener("input", update);
  update();
})();
