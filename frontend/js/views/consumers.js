/* =====================================================================
   views/consumers.js — consumer search + profile lookup
   ===================================================================== */

const ConsumersView = (function () {

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">
        <div class="card">
          <div class="card-header">🔍 उपभोक्ता खोज / Consumer Search</div>
          <div class="card-body">
            <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
              <input id="co-account" class="form-input" placeholder="Account number" />
              <input id="co-sc" class="form-input" placeholder="SC number" />
              <input id="co-name" class="form-input" placeholder="Name (fuzzy)" />
              <input id="co-father" class="form-input" placeholder="Father" />
              <input id="co-village" class="form-input" placeholder="Village" />
            </div>
            <div class="flex gap-2 mt-3">
              <button id="co-go" class="btn btn-primary">Search</button>
              <button id="co-clear" class="btn btn-secondary">Clear</button>
            </div>
          </div>
        </div>

        <div id="co-results" class="card hidden">
          <div class="card-header">Results</div>
          <div id="co-list" class="card-body p-0"></div>
        </div>
      </div>`;

    document.getElementById("co-go").addEventListener("click", run);
    document.getElementById("co-clear").addEventListener("click", () => {
      ["co-account","co-sc","co-name","co-father","co-village"].forEach(id => document.getElementById(id).value = "");
      document.getElementById("co-results").classList.add("hidden");
    });

    document.querySelectorAll(".card-body input").forEach(i =>
      i.addEventListener("keydown", e => { if (e.key === "Enter") run(); }));
  }

  async function run() {
    const params = {
      account: document.getElementById("co-account").value || undefined,
      sc:      document.getElementById("co-sc").value      || undefined,
      name:    document.getElementById("co-name").value    || undefined,
      father:  document.getElementById("co-father").value  || undefined,
      village: document.getElementById("co-village").value || undefined,
    };
    if (!Object.values(params).some(Boolean)) {
      UI.toast("Provide at least one search parameter.", "warn");
      return;
    }
    const list = document.getElementById("co-list");
    document.getElementById("co-results").classList.remove("hidden");
    list.innerHTML = UI.spinner("Searching…");
    try {
      const r = await API.searchConsumers(params);
      const hits = r.data || [];
      if (!hits.length) { list.innerHTML = UI.empty("No matches."); return; }
      list.innerHTML = `
        <table class="data-table w-full">
          <thead><tr><th>Match</th><th>Account</th><th>Name</th><th>Father</th>
                     <th>Village</th><th>Mobile</th><th>Category</th><th></th></tr></thead>
          <tbody>${hits.map(h => {
            const c = h.record || {};
            return `<tr>
              <td><span class="text-xs text-slate-500">${h.source}</span>
                  <span class="ml-1 px-1.5 py-0.5 text-xs rounded bg-slate-100">${(h.confidence*100).toFixed(0)}%</span></td>
              <td class="font-mono text-xs">${UI.escape(c.account_number)}</td>
              <td class="font-medium">${UI.escape(c.name || "—")}</td>
              <td>${UI.escape(c.father_name || "—")}</td>
              <td>${UI.escape(c.village || "—")}</td>
              <td>${UI.escape(c.mobile || "—")}</td>
              <td>${UI.escape(c.category || "—")}</td>
              <td><a class="btn btn-secondary btn-sm" href="#/consumer/${encodeURIComponent(c.account_number)}">Open</a></td>
            </tr>`;
          }).join("")}
          </tbody></table>`;
    } catch (e) {
      list.innerHTML = UI.errorBox(e);
    }
  }

  // Single consumer profile
  async function renderProfile(root, params) {
    root.innerHTML = UI.spinner("Loading consumer…");
    try {
      const r = await API.getConsumer(params.account);
      const cons = r.data.consumer;
      const hist = r.data.offense_history || {};
      root.innerHTML = `
        <div class="space-y-4">
          <div class="card">
            <div class="card-body grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <h3 class="text-lg font-bold">${UI.escape(cons.name || "—")}</h3>
                <p class="text-sm text-slate-600">S/o ${UI.escape(cons.father_name || "—")}</p>
                <p class="text-xs text-slate-500 mt-1 font-mono">${UI.escape(cons.account_number)}</p>
              </div>
              <div class="text-sm">
                <p>📍 ${UI.escape(cons.village || "—")}, ${UI.escape(cons.post_office || "")}</p>
                <p>📞 ${UI.escape(cons.mobile || "—")}</p>
                <p>🏷️ ${UI.escape(cons.category || "—")}</p>
              </div>
              <div class="text-sm">
                <p>⚡ Load: ${UI.number(cons.load_value)} ${UI.escape(cons.load_unit||"")}</p>
                <p>🏢 Sub-Station: ${UI.escape(cons.sub_substation || "—")}</p>
                <p>📁 Division: ${UI.escape(cons.div_code || "—")}</p>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header flex items-center justify-between">
              <span>📚 Offense History</span>
              <span class="text-xs text-slate-500">
                Total: ${hist.total_offenses || 0} ·
                ${UI.money(hist.total_previous_assessment)}
              </span>
            </div>
            <div class="card-body p-0">
              ${(hist.history && hist.history.length) ? `
                <table class="data-table w-full">
                  <thead><tr><th>#</th><th>Source</th><th>Date</th><th>Section</th>
                             <th class="text-right">Assessment</th><th>FIR</th></tr></thead>
                  <tbody>${hist.history.map((h,i) => `
                    <tr><td>${i+1}</td>
                        <td class="text-xs text-slate-500">${UI.escape(h._src)}</td>
                        <td>${UI.date(h.case_date || h.inspection_date)}</td>
                        <td>${UI.escape(h.section || "—")}</td>
                        <td class="text-right">${UI.money(h.assessment_amount || h.total_assessment)}</td>
                        <td>${UI.escape(h.fir_number || "—")}</td>
                    </tr>`).join("")}
                  </tbody>
                </table>` : UI.empty("Clean record — no previous offenses.")}
            </div>
          </div>

          <div class="text-center"><a href="#/new-raid" class="btn btn-primary">＋ New Raid for this Consumer</a></div>
        </div>`;
    } catch (e) {
      root.innerHTML = UI.errorBox(e);
    }
  }

  return { render, renderProfile };
})();
