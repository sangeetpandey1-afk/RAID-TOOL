/* =====================================================================
   views/settings.js — view system config & health
   ===================================================================== */

const SettingsView = (function () {

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">
        <div class="card">
          <div class="card-header">⚙️ System Configuration</div>
          <div id="st-config" class="card-body">${UI.spinner()}</div>
        </div>

        <div class="card">
          <div class="card-header">🩺 Server Health</div>
          <div id="st-health" class="card-body">${UI.spinner()}</div>
        </div>

        <div class="card">
          <div class="card-header">📑 Document Templates</div>
          <div id="st-templates" class="card-body">${UI.spinner()}</div>
        </div>
      </div>`;

    const [cfg, hp, dk] = await Promise.allSettled([
      API.systemConfig(),
      API.health(),
      API.documentKinds(),
    ]);

    paintConfig(document.getElementById("st-config"), cfg);
    paintHealth(document.getElementById("st-health"), hp);
    paintTemplates(document.getElementById("st-templates"), dk);
  }

  function paintConfig(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const cfg = settled.value.data || {};
    el.innerHTML = `
      <table class="data-table w-full">
        <thead><tr><th>Key</th><th>Value</th></tr></thead>
        <tbody>${Object.entries(cfg).map(([k,v]) =>
          `<tr><td class="font-mono text-xs">${UI.escape(k)}</td>
               <td class="font-medium">${UI.escape(v)}</td></tr>`).join("")}
        </tbody></table>`;
  }

  function paintHealth(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const d = settled.value.data || {};
    el.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div class="bg-slate-50 rounded p-3"><div class="text-xs text-slate-500">Status</div>
          <div class="font-bold ${d.db_ok ? 'text-emerald-700' : 'text-red-700'}">${UI.escape(d.status || "—")}</div></div>
        <div class="bg-slate-50 rounded p-3"><div class="text-xs text-slate-500">Version</div>
          <div class="font-medium">${UI.escape(d.version)}</div></div>
        <div class="bg-slate-50 rounded p-3"><div class="text-xs text-slate-500">Python</div>
          <div class="font-medium">${UI.escape(d.python)}</div></div>
        <div class="bg-slate-50 rounded p-3"><div class="text-xs text-slate-500">SQLite</div>
          <div class="font-medium">${UI.escape(d.sqlite)}</div></div>
      </div>
      <p class="text-xs text-slate-500 mt-3">DB: <code class="bg-slate-100 px-1.5 py-0.5 rounded">${UI.escape(d.db_path)}</code></p>
      <table class="data-table w-full mt-3">
        <thead><tr><th>Table</th><th class="text-right">Row count</th></tr></thead>
        <tbody>${Object.entries(d.table_counts || {}).map(([k, v]) =>
          `<tr><td>${UI.escape(k)}</td><td class="text-right font-medium">${UI.number(v)}</td></tr>`).join("")}
        </tbody></table>`;
  }

  function paintTemplates(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const d = settled.value.data || {};
    el.innerHTML = `
      <p class="text-xs text-slate-500 mb-3">
        Place templates in <code class="bg-slate-100 px-1.5 py-0.5 rounded">templates/</code>
        with placeholders like <code>{{ NAME }}</code>. If template missing, system auto-generates a clean .docx.
      </p>
      <table class="data-table w-full">
        <thead><tr><th>Document Kind</th><th>Template Path</th></tr></thead>
        <tbody>${(d.kinds || []).map(k =>
          `<tr><td class="font-medium">${UI.escape(k)}</td>
               <td class="text-xs font-mono">${UI.escape(d.templates[k])}</td></tr>`).join("")}
        </tbody></table>`;
  }

  return { render };
})();
