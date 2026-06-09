(function () {
  const storageKey = "homelab.sidebar.openMenus";
  const dashboardPath = "/dashboard";
  const menus = Array.from(document.querySelectorAll("[data-sidebar-menu]"));
  const resetLinks = Array.from(document.querySelectorAll("[data-reset-sidebar]"));
  const themeKey = "homelab.theme";
  const themeToggle = document.querySelector("[data-theme-toggle]");

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    if (themeToggle) {
      themeToggle.setAttribute("aria-label", "Toggle light and dark mode");
    }
  }

  function saveState() {
    const openMenus = menus
      .filter((menu) => menu.open)
      .map((menu) => menu.dataset.sidebarMenu);
    localStorage.setItem(storageKey, JSON.stringify(openMenus));
  }

  function clearState() {
    localStorage.removeItem(storageKey);
    menus.forEach((menu) => {
      menu.open = false;
    });
  }

  if (window.location.pathname === dashboardPath) {
    clearState();
  } else {
    try {
      const openMenus = new Set(JSON.parse(localStorage.getItem(storageKey) || "[]"));
      menus.forEach((menu) => {
        menu.open = openMenus.has(menu.dataset.sidebarMenu);
      });
    } catch {
      clearState();
    }
  }

  menus.forEach((menu) => {
    menu.addEventListener("toggle", saveState);
  });

  resetLinks.forEach((link) => {
    link.addEventListener("click", clearState);
  });

  const savedTheme = localStorage.getItem(themeKey) || "dark";
  applyTheme(savedTheme);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      localStorage.setItem(themeKey, nextTheme);
      applyTheme(nextTheme);
    });
  }
})();
