/* =====================================================================
   views/master-data.js — import master Excel files + view devices/rates
   ===================================================================== */

const MasterDataView = (function () {

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">

        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>📁 Master Data Files</span>
            <button id="md-refresh" class="btn btn-secondary btn-sm">↻ Refresh</button>
          </div>
          <div class="card-body">
            <p class="text-sm text-slate-600 mb-3">
              Excel master files ko <code class="bg-slate-100 px-1.5 py-0.5 rounded">master_data/</code>
              folder me daalo aur "Import All" dabao.
            </p>
            <div id="md-files">${UI.spinner()}</div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button id="md-import-all" class="btn btn-primary">⬆ Import All Master Data</button>
              <button data-import="consumers"  class="btn btn-secondary btn-sm">Consumers</button>
              <button data-import="historical" class="btn btn-secondary btn-sm">Historical</button>
              <button data-import="current"    class="btn btn-secondary btn-sm">Current Cases</button>
              <button data-import="devices"    class="btn btn-secondary btn-sm">Devices</button>
              <button data-import="rates"      class="btn btn-secondary btn-sm">Rates</button>
              <button data-import="mapping"    class="btn btn-secondary btn-sm">Account Mapping</button>
            </div>
          </div>
        </div>

        <div id="md-import-result" class="hidden"></div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="card">
            <div class="card-header">⚙️ Devices (${"…"})</div>
            <div id="md-devices" class="card-body p-0">${UI.spinner()}</div>
          </div>
          <div class="card">
            <div class="card-header">💰 Rate Categories</div>
            <div id="md-rates" class="card-body p-0">${UI.spinner()}</div>
          </div>
        </div>
      </div>`;

    bind();
    await refreshAll();
  }

  function bind() {
    document.getElementById("md-refresh").addEventListener("click", refreshAll);
    document.getElementById("md-import-all").addEventListener("click", importAll);
    document.querySelectorAll("[data-import]").forEach(b =>
      b.addEventListener("click", () => importOne(b.dataset.import)));
  }

  async function refreshAll() {
    State.invalidate();
    await Promise.all([renderFiles(), renderDevices(), renderRates()]);
  }

  async function renderFiles() {
    const el = document.getElementById("md-files");
    try {
      const r = await API.masterFiles();
      const map = r.data.files || {};
      el.innerHTML = `
        <div class="text-xs text-slate-500 mb-2">Folder: <code>${UI.escape(r.data.master_data_dir)}</code></div>
        <table class="data-table w-full">
          <thead><tr><th>Kind</th><th>Detected file</th></tr></thead>
          <tbody>${Object.entries(map).map(([k, v]) => `
            <tr><td class="font-medium">${UI.escape(k)}</td>
                <td>${v ? `<span class="text-emerald-700">✓ ${UI.escape(v)}</span>`
                       : `<span class="text-slate-400">—</span>`}</td>
            </tr>`).join("")}</tbody></table>`;
    } catch (e) { el.innerHTML = UI.errorBox(e); }
  }

  async function renderDevices() {
    const el = document.getElementById("md-devices");
    try {
      const r = await API.deviceCategories();
      const cats = r.data || [];
      el.innerHTML = `
        <table class="data-table w-full">
          <thead><tr><th>Category</th><th class="text-right">Devices</th></tr></thead>
          <tbody>${cats.map(c => `
            <tr><td>${UI.escape(c.category || "—")}</td>
                <td class="text-right font-medium">${c.device_count}</td></tr>
          `).join("")}</tbody>
        </table>`;
    } catch (e) { el.innerHTML = UI.errorBox(e); }
  }

  async function renderRates() {
    const el = document.getElementById("md-rates");
    try {
      const r = await API.rateCategories();
      const rows = r.data || [];
      if (!rows.length) {
        el.innerHTML = UI.empty("No rates loaded yet — import slab_rates.xlsx.");
        return;
      }
      el.innerHTML = `
        <table class="data-table w-full">
          <thead><tr><th>Category</th><th>Slabs</th><th>Range</th></tr></thead>
          <tbody>${rows.map(r => `
            <tr><td class="font-medium">${UI.escape(r.category)}</td>
                <td>${r.slab_count}</td>
                <td class="text-xs">${r.lo}-${r.hi}</td></tr>
          `).join("")}</tbody></table>`;
    } catch (e) { el.innerHTML = UI.errorBox(e); }
  }

  async function importAll() {
    const out = document.getElementById("md-import-result");
    out.classList.remove("hidden");
    out.innerHTML = `<div class="card"><div class="card-body">${UI.spinner("Importing… please wait")}</div></div>`;
    try {
      const r = await API.importAllMaster();
      renderImportResult(out, r.data);
      await refreshAll();
      UI.toast(`Imported ${r.data.summary.total_inserted} new + ${r.data.summary.total_updated} updated rows`, "success");
    } catch (e) {
      out.innerHTML = `<div class="card"><div class="card-body">${UI.errorBox(e)}</div></div>`;
    }
  }

  async function importOne(kind) {
    const out = document.getElementById("md-import-result");
    out.classList.remove("hidden");
    out.innerHTML = `<div class="card"><div class="card-body">${UI.spinner(`Importing ${kind}…`)}</div></div>`;
    try {
      const r = await API.importOneMaster(kind);
      out.innerHTML = `
        <div class="card">
          <div class="card-header">Import Report — ${UI.escape(kind)}</div>
          <div class="card-body">${reportHtml(r.data)}</div>
        </div>`;
      await refreshAll();
      UI.toast(`${r.data.inserted} inserted, ${r.data.updated} updated`, "success");
    } catch (e) {
      out.innerHTML = `<div class="card"><div class="card-body">${UI.errorBox(e)}</div></div>`;
    }
  }

  function renderImportResult(out, data) {
    const s = data.summary || {};
    out.innerHTML = `
      <div class="card">
        <div class="card-header">📥 Import Summary</div>
        <div class="card-body">
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm mb-4">
            <div class="bg-emerald-50 rounded p-3"><div class="text-xs text-emerald-700">Inserted</div>
              <div class="text-xl font-bold text-emerald-800">${s.total_inserted}</div></div>
            <div class="bg-blue-50 rounded p-3"><div class="text-xs text-blue-700">Updated</div>
              <div class="text-xl font-bold text-blue-800">${s.total_updated}</div></div>
            <div class="bg-amber-50 rounded p-3"><div class="text-xs text-amber-700">Skipped</div>
              <div class="text-xl font-bold text-amber-800">${s.total_skipped}</div></div>
            <div class="bg-red-50 rounded p-3"><div class="text-xs text-red-700">Errors</div>
              <div class="text-xl font-bold text-red-800">${s.total_errors}</div></div>
            <div class="bg-slate-100 rounded p-3"><div class="text-xs text-slate-700">Files</div>
              <div class="text-xl font-bold text-slate-800">${s.files_imported}</div></div>
          </div>

          <div class="space-y-3">
            ${Object.entries(data.reports || {}).map(([k, rep]) => `
              <details class="border border-slate-200 rounded">
                <summary class="px-3 py-2 cursor-pointer flex items-center justify-between bg-slate-50">
                  <span class="font-medium">${UI.escape(k)}</span>
                  <span class="text-xs text-slate-500">
                    ${rep.inserted} ins · ${rep.updated} upd · ${rep.skipped} skip · ${rep.error_count} err · ${rep.duration_ms}ms
                  </span>
                </summary>
                <div class="p-3 text-sm">${reportHtml(rep)}</div>
              </details>`).join("")}
          </div>
        </div>
      </div>`;
  }

  function reportHtml(rep) {
    return `
      <div class="space-y-2 text-sm">
        ${rep.file_path
          ? `<p>📄 File: <code class="bg-slate-100 px-1.5 py-0.5 rounded text-xs">${UI.escape(rep.file_path)}</code></p>`
          : `<p class="text-slate-400">No file detected.</p>`}
        ${rep.warnings?.length
          ? `<div class="bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800">
               ${rep.warnings.map(w => `• ${UI.escape(w)}`).join("<br>")}
             </div>` : ""}
        <p class="text-xs text-slate-500">
          Total rows: <strong>${rep.total_rows}</strong> · Duration: ${rep.duration_ms}ms
        </p>
        ${Object.keys(rep.column_mapping || {}).length ? `
          <details class="text-xs">
            <summary class="cursor-pointer text-slate-500">Column mapping</summary>
            <table class="w-full mt-1">
              ${Object.entries(rep.column_mapping).map(([k,v]) => `
                <tr><td class="py-0.5">${UI.escape(k)}</td>
                    <td class="py-0.5">→</td>
                    <td class="py-0.5 font-mono">${UI.escape(v)}</td></tr>`).join("")}
            </table>
          </details>` : ""}
        ${rep.errors_sample?.length ? `
          <details class="text-xs">
            <summary class="cursor-pointer text-red-600">${rep.error_count} error(s)</summary>
            <ul class="mt-1 space-y-1">${rep.errors_sample.map(e =>
              `<li>Row ${e.row}: ${UI.escape(e.reason)}</li>`).join("")}</ul>
          </details>` : ""}
      </div>`;
  }

  return { render };
})();
