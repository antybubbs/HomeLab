(function () {
  const storageKey = "homelab.sidebar.openMenus";
  const collapseStorageKey = "homelab.sidebar.collapsed";
  const dashboardPath = "/dashboard";
  const menus = Array.from(document.querySelectorAll("[data-sidebar-menu]"));
  const resetLinks = Array.from(document.querySelectorAll("[data-reset-sidebar]"));
  const collapseButton = document.querySelector("[data-sidebar-collapse]");
  let flyout = null;
  let flyoutOwner = null;
  let flyoutCloseTimer = null;
  document.documentElement.dataset.theme = "dark";
  localStorage.removeItem("homelab.theme");

  function setCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    localStorage.setItem(collapseStorageKey, collapsed ? "1" : "0");
    if (collapseButton) {
      collapseButton.textContent = collapsed ? ">" : "<";
      collapseButton.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
      collapseButton.setAttribute("aria-label", collapseButton.title);
    }
  }

  function saveState() {
    const openMenus = menus
      .filter((menu) => menu.open)
      .map((menu) => menu.dataset.sidebarMenu);
    localStorage.setItem(storageKey, JSON.stringify(openMenus));
  }

  function isCollapsed() {
    return document.body.classList.contains("sidebar-collapsed");
  }

  function closeFlyout() {
    if (flyout) flyout.remove();
    flyout = null;
    flyoutOwner = null;
    window.clearTimeout(flyoutCloseTimer);
    flyoutCloseTimer = null;
  }

  function scheduleFlyoutClose() {
    window.clearTimeout(flyoutCloseTimer);
    flyoutCloseTimer = window.setTimeout(closeFlyout, 180);
  }

  function cancelFlyoutClose() {
    window.clearTimeout(flyoutCloseTimer);
    flyoutCloseTimer = null;
  }

  function openFlyout(menu) {
    if (!isCollapsed()) return;
    const summary = menu.querySelector("summary");
    const children = menu.querySelector(":scope > .nav-children");
    if (!summary || !children) return;
    if (flyoutOwner === menu && flyout) {
      cancelFlyoutClose();
      return;
    }

    closeFlyout();
    flyoutOwner = menu;
    flyout = document.createElement("div");
    flyout.className = "sidebar-flyout-popover";

    const title = document.createElement("div");
    title.className = "sidebar-flyout-title";
    title.textContent = summary.querySelector(".nav-label")?.textContent?.trim() || "Menu";

    const content = children.cloneNode(true);
    content.classList.add("sidebar-flyout-content");
    flyout.append(title, content);
    document.body.appendChild(flyout);

    const rect = summary.getBoundingClientRect();
    const flyoutRect = flyout.getBoundingClientRect();
    const top = Math.max(8, Math.min(rect.top, window.innerHeight - flyoutRect.height - 8));
    flyout.style.left = `${rect.right + 10}px`;
    flyout.style.top = `${top}px`;

    flyout.addEventListener("mouseenter", cancelFlyoutClose);
    flyout.addEventListener("mouseleave", scheduleFlyoutClose);
    flyout.addEventListener("focusin", cancelFlyoutClose);
    flyout.addEventListener("focusout", (event) => {
      if (!flyout?.contains(event.relatedTarget)) scheduleFlyoutClose();
    });
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

  setCollapsed(localStorage.getItem(collapseStorageKey) === "1");

  if (collapseButton) {
    collapseButton.addEventListener("click", () => {
      closeFlyout();
      setCollapsed(!document.body.classList.contains("sidebar-collapsed"));
    });
  }

  menus.forEach((menu) => {
    const summary = menu.querySelector("summary");
    menu.addEventListener("mouseenter", () => openFlyout(menu));
    menu.addEventListener("mouseleave", scheduleFlyoutClose);
    menu.addEventListener("focusin", () => openFlyout(menu));
    menu.addEventListener("focusout", (event) => {
      if (!menu.contains(event.relatedTarget) && !flyout?.contains(event.relatedTarget)) scheduleFlyoutClose();
    });
    if (summary) {
      summary.addEventListener("click", (event) => {
        if (!isCollapsed()) return;
        event.preventDefault();
        if (flyoutOwner === menu && flyout) {
          closeFlyout();
        } else {
          openFlyout(menu);
        }
      });
    }
  });

  document.querySelectorAll(".sidebar a.nav-link[href]").forEach((link) => {
    const href = link.getAttribute("href");
    if (href && (window.location.pathname === href || (!["/dashboard", "/admin"].includes(href) && window.location.pathname.startsWith(href + "/")))) {
      link.classList.add("active");
      link.closest("details")?.setAttribute("open", "");
      link.closest(".nav-group")?.setAttribute("open", "");
    }
  });

  document.addEventListener("click", (event) => {
    if (flyout && !flyout.contains(event.target) && !event.target.closest("[data-sidebar-menu]")) {
      closeFlyout();
    }
    document.querySelectorAll(".account-menu[open]").forEach((menu) => {
      if (!menu.contains(event.target)) {
        menu.open = false;
      }
    });
  });
})();
