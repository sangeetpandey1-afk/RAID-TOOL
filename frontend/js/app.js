/* =====================================================================
   app.js — hash router + view orchestration + bootstrapping
   ===================================================================== */

(function () {

  // --------------------------------------------------- routes
  const ROUTES = [
    { path: /^#?\/?$/,                     view: "dashboard",   title: "Dashboard" },
    { path: /^#\/dashboard$/,              view: "dashboard",   title: "Dashboard" },
    { path: /^#\/new-raid$/,               view: "raid-form",   title: "नया रेड / New Raid" },
    { path: /^#\/cases$/,                  view: "cases",       title: "Cases" },
    { path: /^#\/case\/(.+)$/,             view: "case-detail", title: "Case" },
    { path: /^#\/consumers$/,              view: "consumers",   title: "Consumers" },
    { path: /^#\/consumer\/(.+)$/,         view: "consumer-profile", title: "Consumer" },
    { path: /^#\/master-data$/,            view: "master-data", title: "Master Data" },
    { path: /^#\/settings$/,               view: "settings",    title: "Settings" },
  ];

  function matchRoute(hash) {
    for (const r of ROUTES) {
      const m = hash.match(r.path);
      if (m) return { route: r, params: m.slice(1) };
    }
    return { route: ROUTES[0], params: [] };
  }

  // --------------------------------------------------- view registry
  const VIEWS = {
    dashboard:         (root)         => DashboardView.render(root),
    "raid-form":       (root)         => RaidFormView.render(root),
    cases:             (root)         => CasesView.render(root),
    "case-detail":     (root, params) => CaseDetailView.render(root, { id: decodeURIComponent(params[0]) }),
    consumers:         (root)         => ConsumersView.render(root),
    "consumer-profile":(root, params) => ConsumersView.renderProfile(root, { account: decodeURIComponent(params[0]) }),
    "master-data":     (root)         => MasterDataView.render(root),
    settings:          (root)         => SettingsView.render(root),
  };

  // --------------------------------------------------- nav highlight
  function highlightNav(viewKey) {
    const map = {
      "dashboard": "dashboard",
      "raid-form": "new-raid",
      "cases": "cases", "case-detail": "cases",
      "consumers": "consumers", "consumer-profile": "consumers",
      "master-data": "master-data",
      "settings": "settings",
    };
    const key = map[viewKey];
    document.querySelectorAll(".nav-link").forEach(a => {
      a.classList.toggle("active", a.dataset.nav === key);
    });
  }

  // --------------------------------------------------- main render
  async function go() {
    const hash = window.location.hash || "#/dashboard";
    const { route, params } = matchRoute(hash);
    console.log("[Router] Navigating to:", hash, "→", route.view);
    document.getElementById("page-title").textContent = route.title;
    highlightNav(route.view);

    const root = document.getElementById("view");
    root.innerHTML = UI.spinner();
    try {
      await VIEWS[route.view](root, params);
    } catch (e) {
      console.error("[Router] View render failed:", e);
      root.innerHTML = UI.errorBox(e);
    }
  }

  // --------------------------------------------------- bootstrap
  async function boot() {
    // Top bar — current date
    document.getElementById("current-date").textContent =
      new Date().toLocaleDateString("en-IN", {
        weekday: "long", day: "numeric", month: "long", year: "numeric",
      });

    // Refresh button reloads the current view
    document.getElementById("refresh-btn").addEventListener("click", () => {
      State.invalidate();
      go();
    });

    // Health badge
    refreshHealthBadge();
    setInterval(refreshHealthBadge, 30000);

    // Hash changes
    window.addEventListener("hashchange", go);

    // Initial render
    go();
  }

  async function refreshHealthBadge() {
    const badge = document.getElementById("server-status");
    try {
      const h = await State.getHealth(true);
      const ok = h && h.db_ok;
      badge.innerHTML = `
        <span class="w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'} mr-1.5"></span>
        ${ok ? "Online" : "DB issue"}`;
    } catch (_) {
      badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-400 mr-1.5"></span>Offline`;
    }
  }

  // start
  console.log("[App] Booting Raid Management System…");
  console.log("[App] API base:", typeof API !== "undefined" ? "API loaded" : "API MISSING!");
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    // DOM already ready (scripts are at end of body)
    boot();
  }
})();
