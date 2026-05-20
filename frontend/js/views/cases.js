/* =====================================================================
   views/cases.js — search & list cases with multi-parameter filter
   ===================================================================== */

const CasesView = (function () {

  const state = {
    page: 1, pageSize: 25,
    filters: {},
  };

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">
        <div class="card">
          <div class="card-header">🔎 Search Cases</div>
          <div class="card-body">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div><label class="form-label">Quick search</label>
                <input id="cs-q" class="form-input" placeholder="account / name / online_no / FIR" /></div>
              <div><label class="form-label">Section</label>
                <select id="cs-section" class="form-select">
                  <option value="">Any</option>
                  <option value="135">135</option><option value="138">138</option>
                  <option value="126">126</option><option value="Other">Other</option>
                </select></div>
              <div><label class="form-label">Status</label>
                <select id="cs-status" class="form-select">
                  <option value="">Any</option>
                  <option value="open">Open</option>
                  <option value="noticed">Noticed</option>
                  <option value="partial">Partial</option>
                  <option value="paid">Paid</option>
                  <option value="section3_sent">Sec 3 Sent</option>
                  <option value="section5_sent">Sec 5 Sent</option>
                  <option value="closed">Closed</option>
                  <option value="revised">Revised</option>
                </select></div>
              <div><label class="form-label">JE Name</label>
                <input id="cs-je" class="form-input" /></div>
              <div><label class="form-label">From Date</label>
                <input id="cs-from" type="date" class="form-input" /></div>
              <div><label class="form-label">To Date</label>
                <input id="cs-to" type="date" class="form-input" /></div>
              <div><label class="form-label">Min Amount</label>
                <input id="cs-min" type="number" class="form-input" /></div>
              <div><label class="form-label">Max Amount</label>
                <input id="cs-max" type="number" class="form-input" /></div>
            </div>
            <div class="flex gap-2 mt-4">
              <button id="cs-go" class="btn btn-primary">🔎 Search</button>
              <button id="cs-clear" class="btn btn-secondary">Clear</button>
              <a href="#/new-raid" class="btn btn-success ml-auto">＋ New Raid</a>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>Results</span>
            <span id="cs-meta" class="text-xs text-slate-500"></span>
          </div>
          <div id="cs-list" class="card-body p-0">${UI.spinner("Loading cases…")}</div>
        </div>
      </div>`;

    bind(root);
    await load();
  }

  function bind(root) {
    const $ = (s) => root.querySelector(s);
    $("#cs-go").addEventListener("click", () => { state.page = 1; load(); });
    $("#cs-clear").addEventListener("click", () => {
      ["cs-q", "cs-section", "cs-status", "cs-je", "cs-from", "cs-to", "cs-min", "cs-max"]
        .forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
      state.page = 1; load();
    });
    $("#cs-q").addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); state.page = 1; load(); }
    });
  }

  async function load() {
    const $ = (id) => document.getElementById(id).value;
    const params = {
      q: $("cs-q") || undefined,
      section: $("cs-section") || undefined,
      status: $("cs-status") || undefined,
      je_name: $("cs-je") || undefined,
      from_date: $("cs-from") || undefined,
      to_date: $("cs-to") || undefined,
      min_amount: $("cs-min") || undefined,
      max_amount: $("cs-max") || undefined,
      page: state.page, page_size: state.pageSize,
    };
    const list = document.getElementById("cs-list");
    list.innerHTML = UI.spinner("Searching…");
    try {
      const r = await API.searchCases(params);
      renderList(r);
    } catch (e) {
      list.innerHTML = UI.errorBox(e);
    }
  }

  function renderList(r) {
    const list = document.getElementById("cs-list");
    const meta = document.getElementById("cs-meta");
    const rows = r.data || [];
    const m = r.meta || {};
    meta.textContent = `${m.total ?? rows.length} cases — page ${m.page}/${m.pages}`;
    if (!rows.length) { list.innerHTML = UI.empty("No cases match these filters."); return; }

    list.innerHTML = `
      <table class="data-table w-full">
        <thead><tr>
          <th>Case ID</th><th>Online No</th><th>Account</th><th>Name</th>
          <th>Section</th><th>Date</th>
          <th class="text-right">Assessment</th>
          <th class="text-right">Compounding</th>
          <th>Status</th>
        </tr></thead>
        <tbody>${rows.map(c => `
          <tr class="cursor-pointer" data-cid="${UI.escape(c.case_id)}">
            <td><a href="#/case/${encodeURIComponent(c.case_id)}" class="text-brand-600 font-mono hover:underline">${UI.escape(c.case_id)}</a></td>
            <td>${UI.escape(c.online_no || "—")}</td>
            <td class="font-mono text-xs">${UI.escape(c.account_number || "—")}</td>
            <td>${UI.escape(c.user_name || "—")}</td>
            <td>${UI.escape(c.section || "—")}</td>
            <td class="text-xs text-slate-500">${UI.date(c.inspection_date)}</td>
            <td class="text-right font-medium">${UI.money(c.total_assessment)}</td>
            <td class="text-right">${UI.money(c.compounding_amount)}</td>
            <td>${UI.statusBadge(c.case_status)}</td>
          </tr>`).join("")}
        </tbody></table>

      <div class="flex items-center justify-between p-3 border-t border-slate-200 bg-slate-50">
        <button id="cs-prev" class="btn btn-secondary btn-sm" ${state.page <= 1 ? "disabled" : ""}>← Prev</button>
        <span class="text-xs text-slate-500">Page ${m.page} of ${m.pages}</span>
        <button id="cs-next" class="btn btn-secondary btn-sm" ${state.page >= (m.pages || 1) ? "disabled" : ""}>Next →</button>
      </div>`;

    document.getElementById("cs-prev").addEventListener("click", () => { state.page--; load(); });
    document.getElementById("cs-next").addEventListener("click", () => { state.page++; load(); });
  }

  return { render };
})();
