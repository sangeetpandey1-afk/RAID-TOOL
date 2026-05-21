/* =====================================================================
   views/master-data.js — import master Excel files + view devices/rates
                         + RATE SCHEDULE UPLOAD with version management
   ===================================================================== */

const MasterDataView = (function () {

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">

        <!-- ========== Master Data Files ========== -->
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
              <button data-import="rates"      class="btn btn-secondary btn-sm">Rates (folder)</button>
              <button data-import="mapping"    class="btn btn-secondary btn-sm">Account Mapping</button>
            </div>
          </div>
        </div>

        <div id="md-import-result" class="hidden"></div>

        <!-- ========== RATE SCHEDULE UPLOAD (NEW!) ========== -->
        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>📊 Rate Schedule Upload / दर अनुसूची अपलोड</span>
            <span class="text-xs text-slate-500">Upload slab_rates.xlsx with new effective date</span>
          </div>
          <div class="card-body">
            <p class="text-sm text-slate-600 mb-3">
              नई दर अनुसूची (LMV-1 से LMV-9 सभी categories) Excel file upload करें।
              Columns: <code>Category, SlabStart, SlabEnd, RatePerUnit, FixedCharge, DutyPercent, Condition, EffectiveDate</code>
            </p>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4 p-4 bg-slate-50 rounded border border-slate-200">
              <div class="md:col-span-2">
                <label class="form-label req">Excel File (.xlsx)</label>
                <input id="rate-file" type="file" accept=".xlsx,.xls,.xlsm"
                       class="form-input file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-brand-600 file:text-white file:cursor-pointer" />
              </div>
              <div>
                <label class="form-label req">Effective Date / प्रभावी तिथि</label>
                <input id="rate-eff-date" type="date" class="form-input" />
              </div>
              <div>
                <label class="form-label">Replace Old?</label>
                <select id="rate-replace" class="form-select">
                  <option value="false">No — Keep old rates active</option>
                  <option value="true">Yes — Deactivate old rates for same categories</option>
                </select>
              </div>
            </div>

            <div class="flex gap-2 mb-4">
              <button id="rate-upload-btn" class="btn btn-success">
                ⬆ Upload Rate Schedule
              </button>
              <span id="rate-upload-status" class="text-sm text-slate-500 self-center"></span>
            </div>

            <div id="rate-upload-result" class="hidden"></div>
          </div>
        </div>

        <!-- ========== Rate Version History ========== -->
        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>📅 Rate Schedule Versions</span>
            <span class="text-xs text-slate-500">Effective dates in system</span>
          </div>
          <div id="md-rate-versions" class="card-body p-0">${UI.spinner()}</div>
        </div>

        <!-- ========== Devices + Rates detail ========== -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="card">
            <div class="card-header">⚙️ Devices</div>
            <div id="md-devices" class="card-body p-0">${UI.spinner()}</div>
          </div>
          <div class="card">
            <div class="card-header flex items-center justify-between">
              <span>💰 Rate Categories (Active)</span>
              <span class="text-xs text-slate-500" id="md-rate-count"></span>
            </div>
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

    // Rate upload
    document.getElementById("rate-upload-btn").addEventListener("click", uploadRateSchedule);
  }

  async function refreshAll() {
    State.invalidate();
    await Promise.all([renderFiles(), renderDevices(), renderRates(), renderRateVersions()]);
  }

  // ========== Master Files ==========
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

  // ========== Devices ==========
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

  // ========== Rate Categories (expanded) ==========
  async function renderRates() {
    const el = document.getElementById("md-rates");
    const countEl = document.getElementById("md-rate-count");
    try {
      const r = await API.rateCategories();
      const rows = r.data || [];
      if (countEl) countEl.textContent = `${rows.length} categories`;
      if (!rows.length) {
        el.innerHTML = UI.empty("No rates loaded — upload slab_rates.xlsx above.");
        return;
      }
      el.innerHTML = `
        <table class="data-table w-full text-sm">
          <thead><tr>
            <th>Category</th>
            <th class="text-right">Slabs</th>
            <th class="text-right">Fixed ₹</th>
            <th class="text-right">ED %</th>
            <th>Effective</th>
          </tr></thead>
          <tbody>${rows.map(r => `
            <tr>
              <td class="font-medium">${UI.escape(r.category)}</td>
              <td class="text-right">${r.slab_count}</td>
              <td class="text-right">${r.fixed_charge_max ? `₹${UI.number(r.fixed_charge_min)}–${UI.number(r.fixed_charge_max)}` : "—"}</td>
              <td class="text-right">${r.avg_ed_percent != null ? `${Number(r.avg_ed_percent).toFixed(1)}%` : "—"}</td>
              <td class="text-xs text-slate-500">${UI.date(r.latest_effective_date)}</td>
            </tr>
          `).join("")}</tbody></table>`;
    } catch (e) { el.innerHTML = UI.errorBox(e); }
  }

  // ========== Rate Version History ==========
  async function renderRateVersions() {
    const el = document.getElementById("md-rate-versions");
    try {
      const r = await API.request("/api/rates/effective-dates");
      const rows = r.data || [];
      if (!rows.length) {
        el.innerHTML = `<div class="p-4 text-sm text-slate-400">No rate versions found. Upload a rate schedule above.</div>`;
        return;
      }
      el.innerHTML = `
        <table class="data-table w-full">
          <thead><tr>
            <th>Effective Date / प्रभावी तिथि</th>
            <th class="text-right">Slabs</th>
            <th class="text-right">Actions</th>
          </tr></thead>
          <tbody>${rows.map(v => `
            <tr>
              <td class="font-medium">${UI.date(v.effective_date)}</td>
              <td class="text-right">${v.slab_count} slabs</td>
              <td class="text-right">
                <button class="btn btn-danger btn-sm" data-del-rate="${UI.escape(v.effective_date)}"
                        title="Deactivate this version">🗑 Deactivate</button>
              </td>
            </tr>`).join("")}
          </tbody>
        </table>`;

      // Bind delete buttons
      el.querySelectorAll("[data-del-rate]").forEach(btn => {
        btn.addEventListener("click", async () => {
          const dt = btn.dataset.delRate;
          if (!await UI.confirm(`Deactivate all rates for date ${dt}? (Can be re-activated later)`, { danger: true })) return;
          try {
            await API.request(`/api/rates/by-date/${encodeURIComponent(dt)}`, { method: "DELETE" });
            UI.toast(`Rates for ${dt} deactivated.`, "success");
            await refreshAll();
          } catch (e) { UI.toast(e.message, "error"); }
        });
      });
    } catch (e) { el.innerHTML = UI.errorBox(e); }
  }

  // ========== Rate Schedule Upload ==========
  async function uploadRateSchedule() {
    const fileInput = document.getElementById("rate-file");
    const effDate = document.getElementById("rate-eff-date").value;
    const replace = document.getElementById("rate-replace").value;
    const statusEl = document.getElementById("rate-upload-status");
    const resultEl = document.getElementById("rate-upload-result");

    if (!fileInput.files || !fileInput.files.length) {
      UI.toast("Excel file select karo!", "warn");
      return;
    }
    if (!effDate) {
      UI.toast("Effective date daalo!", "warn");
      return;
    }

    const file = fileInput.files[0];
    statusEl.textContent = `Uploading ${file.name}…`;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("effective_date", effDate);
    formData.append("replace", replace);

    try {
      const resp = await fetch("/api/rates/upload", {
        method: "POST",
        body: formData,
        // Note: Don't set Content-Type — browser sets multipart boundary automatically
      });
      const payload = await resp.json();

      if (!resp.ok || !payload.ok) {
        throw new Error(payload.error || `HTTP ${resp.status}`);
      }

      const d = payload.data;
      statusEl.textContent = "";
      resultEl.classList.remove("hidden");
      resultEl.innerHTML = `
        <div class="bg-emerald-50 border border-emerald-200 rounded p-4">
          <h4 class="font-semibold text-emerald-800 mb-2">✅ Upload Successful!</h4>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
            <div><span class="text-slate-600">Inserted:</span> <strong class="text-emerald-800">${d.inserted}</strong></div>
            <div><span class="text-slate-600">Skipped:</span> <strong>${d.skipped}</strong></div>
            <div><span class="text-slate-600">Deactivated (old):</span> <strong>${d.deactivated}</strong></div>
            <div><span class="text-slate-600">Errors:</span> <strong class="text-red-700">${d.error_count}</strong></div>
          </div>
          <div class="text-sm">
            <p><strong>Categories:</strong> ${d.categories.join(", ")}</p>
            <p><strong>Effective Date:</strong> ${d.effective_date}</p>
            <p class="text-xs text-slate-500 mt-1">Saved as: ${UI.escape(d.saved_as)}</p>
          </div>
          ${d.error_count > 0 ? `
            <details class="mt-2 text-xs text-red-700">
              <summary class="cursor-pointer">${d.error_count} error(s)</summary>
              <ul class="mt-1 space-y-1">${(d.errors_sample||[]).map(e =>
                `<li>Row ${e.row}: ${UI.escape(e.error)}</li>`).join("")}</ul>
            </details>` : ""}
          ${Object.keys(d.columns_found || {}).length ? `
            <details class="mt-2 text-xs text-slate-500">
              <summary class="cursor-pointer">Column mapping</summary>
              <table class="w-full mt-1">
                ${Object.entries(d.columns_found).map(([k,v]) =>
                  `<tr><td>${UI.escape(k)}</td><td>→</td><td class="font-mono">${UI.escape(v)}</td></tr>`).join("")}
              </table>
            </details>` : ""}
        </div>`;

      UI.toast(`${d.inserted} rate slabs imported for ${d.categories.length} categories`, "success");
      await refreshAll();

    } catch (e) {
      statusEl.textContent = "";
      resultEl.classList.remove("hidden");
      resultEl.innerHTML = UI.errorBox(e);
      UI.toast("Upload failed: " + e.message, "error");
    }
  }

  // ========== Folder-based imports ==========
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
              `<li>Row ${e.row}: ${UI.escape(e.reason || e.error)}</li>`).join("")}</ul>
          </details>` : ""}
      </div>`;
  }

  return { render };
})();
