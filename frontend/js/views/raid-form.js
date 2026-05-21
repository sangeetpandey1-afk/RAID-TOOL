/* =====================================================================
   views/raid-form.js — three-tier raid case entry
       Top:    Consumer info + auto-fill from account
       Middle: LFHD device list + live calculation
       Bottom: Previous offense history + multiplier suggestion
   ===================================================================== */

const RaidFormView = (function () {

  // ---- form state (in-memory) ----
  const state = {
    consumer: null,        // resolved from account search
    devices: [],           // [{name, load, factor, hours, days}]
    section: "135",
    multiplier: 2,
    offenseCount: 0,
    isRepeat: false,
    lastCalc: null,        // assessment dict from /api/calculate
    lastCompounding: null, // result of /api/compounding
    saving: false,
  };

  function reset() {
    state.consumer = null;
    state.devices = [];
    state.section = "135";
    state.multiplier = 2;
    state.offenseCount = 0;
    state.isRepeat = false;
    state.lastCalc = null;
    state.lastCompounding = null;
  }

  async function render(root) {
    reset();
    root.innerHTML = `
      <div class="space-y-6">
        ${tierConsumer()}
        ${tierLFHD()}
        ${tierHistory()}

        <!-- save bar -->
        <div class="card sticky bottom-0 z-10">
          <div class="card-body flex flex-wrap items-center justify-between gap-3">
            <div class="text-sm text-slate-600">
              Total: <strong id="save-total" class="text-lg text-slate-900">—</strong>
              &nbsp;|&nbsp; Compounding:
              <strong id="save-compounding" class="text-slate-900">—</strong>
            </div>
            <div class="flex gap-2">
              <button id="btn-calc" class="btn btn-secondary">🧮 Calculate</button>
              <button id="btn-save" class="btn btn-primary">💾 Save Case</button>
            </div>
          </div>
        </div>
      </div>`;

    bindEvents(root);
    addDeviceRow();          // start with 1 empty row

    // Pre-load device list for dropdown
    await State.getDevices();
    refreshDeviceDatalist(root);
  }

  // ----------------------------------------------------------------- TIER 1
  function tierConsumer() {
    return `
      <div class="card">
        <div class="card-header">📋 Consumer Information</div>
        <div class="card-body">

          <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
            <div class="md:col-span-2">
              <label class="form-label req">Account Number</label>
              <div class="flex gap-2">
                <input id="rf-account" class="form-input" placeholder="e.g. 1234567890" />
                <button id="rf-search" class="btn btn-secondary">🔍 Search</button>
              </div>
            </div>
            <div>
              <label class="form-label">Section</label>
              <select id="rf-section" class="form-select">
                <option value="135" selected>135 - Theft</option>
                <option value="138">138 - TD</option>
                <option value="126">126 - UUE</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div>
              <label class="form-label">Inspection Date</label>
              <input id="rf-inspection-date" type="date" class="form-input" />
            </div>
          </div>

          <div id="rf-section-other" class="mb-4 hidden">
            <label class="form-label">Custom Section / प्रकार</label>
            <input id="rf-section-other-input" class="form-input" placeholder="e.g. 153" />
          </div>

          <div id="rf-td-date-block" class="mb-4 hidden">
            <label class="form-label req">TD Date (Section 138)</label>
            <input id="rf-td-date" type="date" class="form-input" />
            <p class="text-xs text-slate-500 mt-1">Days will be calculated from TD date to today.</p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <div>
              <label class="form-label">Name / नाम</label>
              <input id="rf-name" class="form-input" />
            </div>
            <div>
              <label class="form-label">Father Name / पिता</label>
              <input id="rf-father" class="form-input" />
            </div>
            <div>
              <label class="form-label">Mobile</label>
              <input id="rf-mobile" class="form-input" />
            </div>
            <div>
              <label class="form-label">Village / ग्राम</label>
              <input id="rf-village" class="form-input" />
            </div>
            <div>
              <label class="form-label">Post Office / डाकघर</label>
              <input id="rf-post" class="form-input" />
            </div>
            <div>
              <label class="form-label">Pin Code</label>
              <input id="rf-pin" class="form-input" />
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label class="form-label req">Category / श्रेणी</label>
              <select id="rf-category" class="form-select">
                <option value="">— Loading… —</option>
              </select>
              <p id="rf-cat-info" class="text-xs text-slate-500 mt-1"></p>
            </div>
            <div>
              <label class="form-label">Connected Load (KW)</label>
              <input id="rf-cload" type="number" step="0.001" class="form-input" />
            </div>
            <div>
              <label class="form-label">J.E. Name</label>
              <input id="rf-je" class="form-input" />
            </div>
            <div>
              <label class="form-label">Sub Substation</label>
              <input id="rf-substation" class="form-input" />
            </div>
            <div>
              <label class="form-label">Online No.</label>
              <input id="rf-online" class="form-input" />
            </div>
            <div>
              <label class="form-label">Checking Type</label>
              <select id="rf-checking" class="form-select">
                <option value="">—</option>
                <option value="Regular">Regular</option>
                <option value="Vigilance">Vigilance</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div>
              <label class="form-label">FIR Number</label>
              <input id="rf-fir" class="form-input" />
            </div>
            <div>
              <label class="form-label">Multiplier</label>
              <input id="rf-multiplier" type="number" step="0.5" class="form-input" value="2" />
            </div>
          </div>

        </div>
      </div>`;
  }

  // ----------------------------------------------------------------- TIER 2
  function tierLFHD() {
    return `
      <div class="card">
        <div class="card-header flex items-center justify-between">
          <span>⚡ LFHD Calculation Workspace</span>
          <button id="rf-add-device" class="btn btn-secondary btn-sm">＋ Add Device</button>
        </div>
        <div class="card-body p-0">
          <table class="data-table w-full">
            <thead>
              <tr>
                <th class="w-1/3">Device / उपकरण</th>
                <th class="w-24">Load (W)</th>
                <th class="w-20">Factor</th>
                <th class="w-24">Hours/day</th>
                <th class="w-20">Days</th>
                <th class="w-32 text-right">Units (kWh)</th>
                <th class="w-12"></th>
              </tr>
            </thead>
            <tbody id="rf-devices"></tbody>
            <tfoot class="bg-slate-50">
              <tr>
                <td colspan="5" class="text-right font-semibold py-3">Total Units:</td>
                <td class="text-right font-bold text-lg" id="rf-total-units">0</td>
                <td></td>
              </tr>
            </tfoot>
          </table>

          <datalist id="rf-device-list"></datalist>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 border-t border-slate-200 bg-slate-50">
            <div>
              <label class="form-label">Less Unit (consumed in last year, optional)</label>
              <input id="rf-less-unit" type="number" step="0.01" class="form-input" />
            </div>
            <div>
              <label class="form-label">Override Days (optional)</label>
              <input id="rf-days-override" type="number" class="form-input" placeholder="auto from section" />
            </div>
            <div>
              <label class="form-label">ED % (optional)</label>
              <input id="rf-ed" type="number" step="0.1" class="form-input" placeholder="from rate master" />
            </div>
          </div>
        </div>
      </div>

      <!-- Calculation result panel -->
      <div id="rf-calc-result" class="card hidden">
        <div class="card-header">📊 Assessment Breakdown</div>
        <div id="rf-calc-body" class="card-body"></div>
      </div>`;
  }

  // ----------------------------------------------------------------- TIER 3
  function tierHistory() {
    return `
      <div class="card">
        <div class="card-header flex items-center justify-between">
          <span>📚 पुराने अपराध विवरण / Previous Offense History</span>
          <span id="rf-history-summary" class="text-xs text-slate-500"></span>
        </div>
        <div id="rf-history" class="card-body">
          <p class="text-sm text-slate-500">Search a consumer to see previous offenses.</p>
        </div>
      </div>`;
  }

  // ============================================================
  // Event wiring
  // ============================================================
  function bindEvents(root) {
    const $ = (s) => root.querySelector(s);

    // Default inspection date = today
    $("#rf-inspection-date").value = new Date().toISOString().slice(0, 10);

    $("#rf-section").addEventListener("change", (e) => {
      state.section = e.target.value;
      $("#rf-td-date-block").classList.toggle("hidden", state.section !== "138");
      $("#rf-section-other").classList.toggle("hidden", state.section !== "Other");
    });

    $("#rf-multiplier").addEventListener("input", (e) => {
      state.multiplier = parseFloat(e.target.value) || 2;
    });

    // Category dropdown — show rate info on change
    $("#rf-category").addEventListener("change", onCategoryChange);

    $("#rf-search").addEventListener("click", searchConsumer);
    $("#rf-account").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); searchConsumer(); }
    });

    $("#rf-add-device").addEventListener("click", () => addDeviceRow());

    $("#btn-calc").addEventListener("click", recalc);
    $("#btn-save").addEventListener("click", saveCase);

    // Recalculate on any device-row blur
    $("#rf-devices").addEventListener("change", () => recalc());

    // Load category dropdown
    loadCategoryDropdown();
  }

  // ============================================================
  // Dynamic Category Dropdown (all LMV variants from rate_master)
  // ============================================================
  let _rateCache = null; // [{category, effective_date, fixed_charge, duty_percent, slabs:[]}]

  async function loadCategoryDropdown() {
    const sel = document.getElementById("rf-category");
    if (!sel) return;
    try {
      const r = await API.request("/api/rates/full");
      _rateCache = r.data || [];
      sel.innerHTML = '<option value="">— Select Category —</option>';
      for (const cat of _rateCache) {
        const opt = document.createElement("option");
        opt.value = cat.category;
        const fc = cat.fixed_charge ? ` | Fixed ₹${cat.fixed_charge}` : "";
        const ed = cat.duty_percent ? ` | ED ${cat.duty_percent}%` : "";
        opt.textContent = `${cat.category}${fc}${ed}`;
        sel.appendChild(opt);
      }
      // If consumer already has a category, pre-select it
      if (state.consumer && state.consumer.category) {
        sel.value = state.consumer.category;
        onCategoryChange();
      } else {
        // Default to LMV-1 if available
        const hasLMV1 = _rateCache.find(c => c.category === "LMV-1");
        if (hasLMV1) {
          sel.value = "LMV-1";
          onCategoryChange();
        }
      }
    } catch (e) {
      console.warn("Failed to load rate categories:", e.message);
      // Fallback: allow manual entry
      sel.innerHTML = `
        <option value="">— No rates loaded —</option>
        <option value="LMV-1">LMV-1</option>
        <option value="LMV-1 URBAN">LMV-1 URBAN</option>
        <option value="LMV-2">LMV-2</option>
        <option value="LMV-2 RURAL">LMV-2 RURAL</option>
        <option value="LMV-3 GRAM">LMV-3 GRAM</option>
        <option value="LMV-3 NAGAR">LMV-3 NAGAR</option>
        <option value="LMV-4 SARKARI">LMV-4 SARKARI</option>
        <option value="LMV-4 PRIVATE">LMV-4 PRIVATE</option>
        <option value="LMV-5 RURAL">LMV-5 RURAL</option>
        <option value="LMV-5 URBAN">LMV-5 URBAN</option>
        <option value="LMV-6">LMV-6</option>
        <option value="LMV-7">LMV-7</option>
        <option value="LMV-7 RURAL">LMV-7 RURAL</option>
        <option value="LMV-7 URBAN">LMV-7 URBAN</option>
        <option value="LMV-8">LMV-8</option>
        <option value="LMV-9">LMV-9</option>`;
      sel.value = "LMV-1";
    }
  }

  function onCategoryChange() {
    const sel = document.getElementById("rf-category");
    const info = document.getElementById("rf-cat-info");
    if (!sel || !info) return;
    const cat = sel.value;
    if (!cat || !_rateCache) {
      info.textContent = "";
      return;
    }
    const found = _rateCache.find(c => c.category === cat);
    if (!found) {
      info.textContent = "⚠️ No rate data for this category";
      info.className = "text-xs text-amber-600 mt-1";
      return;
    }
    const slabCount = found.slabs ? found.slabs.length : 0;
    const rates = (found.slabs || []).map(s => `₹${s.rate_per_unit}`).join(", ");
    info.innerHTML = `✅ Fixed: <b>₹${found.fixed_charge || 0}</b> | ED: <b>${found.duty_percent || 0}%</b> | Slabs: ${slabCount} (${rates}) | Effective: ${found.effective_date || "—"}`;
    info.className = "text-xs text-emerald-700 mt-1";
  }

  // ============================================================
  // Consumer search + history fetch
  // ============================================================
  async function searchConsumer() {
    const acct = document.getElementById("rf-account").value.trim();
    if (!acct) { UI.toast("Account number daalo!", "warn"); return; }
    UI.toast("Searching consumer…", "info", 1500);

    try {
      let consumer = null;
      try {
        const r = await API.getConsumer(acct);
        consumer = r.data.consumer;
        renderHistoryFromProfile(r.data);
      } catch (e) {
        if (e.status === 404) {
          // fallback to fuzzy search
          const r = await API.searchConsumers({ account: acct });
          if (r.data && r.data.length) {
            consumer = r.data[0].record;
            UI.toast(`Found via ${r.data[0].source} (confidence ${r.data[0].confidence})`, "info");
            // also fetch full profile for history
            try {
              const full = await API.getConsumer(consumer.account_number);
              renderHistoryFromProfile(full.data);
            } catch (_) { /* ignore */ }
          } else {
            UI.toast("Consumer not found — fill manually.", "warn");
          }
        } else { throw e; }
      }

      if (consumer) {
        state.consumer = consumer;
        fillConsumerFields(consumer);
        UI.toast("Consumer loaded.", "success");
      }

      // ---- offense check (works even for new account)
      try {
        const oc = await API.consumerOffenseCheck(acct, {
          name: consumer?.name || "",
          father: consumer?.father_name || "",
          village: consumer?.village || "",
        });
        applyOffenseCheck(oc.data);
      } catch (_) { /* ignore */ }

    } catch (e) {
      UI.toast(`Search failed: ${e.message}`, "error");
    }
  }

  function fillConsumerFields(c) {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ""; };
    set("rf-name", c.name);
    set("rf-father", c.father_name);
    set("rf-mobile", c.mobile);
    set("rf-village", c.village);
    set("rf-post", c.post_office);
    set("rf-pin", c.pin_code);
    set("rf-cload", c.load_value);
    set("rf-substation", c.sub_substation);
    // Set category dropdown (auto-select from consumer's category)
    const catSel = document.getElementById("rf-category");
    if (catSel && c.category) {
      catSel.value = c.category;
      onCategoryChange();
    }
  }

  function applyOffenseCheck(d) {
    state.offenseCount = d.history?.total_offenses || 0;
    state.isRepeat = !!d.is_repeat_offender;
    if (d.suggested_multiplier) {
      state.multiplier = d.suggested_multiplier;
      document.getElementById("rf-multiplier").value = d.suggested_multiplier;
      UI.toast(`Multiplier auto-set to ${d.suggested_multiplier}x (${d.multiplier_basis} offense)`,
               state.isRepeat ? "warn" : "info");
    }
  }

  function renderHistoryFromProfile(p) {
    const h = (p.offense_history || {});
    const rows = h.history || [];
    const summary = `Total Previous: ${h.total_offenses || 0} | Total Amount: ${UI.money(h.total_previous_assessment)} | ${h.fuzzy_used ? "Fuzzy match" : "Direct match"}`;
    document.getElementById("rf-history-summary").textContent = summary;

    const el = document.getElementById("rf-history");
    if (!rows.length) {
      el.innerHTML = `<p class="text-sm text-emerald-700 font-medium">✅ No previous offenses (first offense — 2× multiplier).</p>`;
      return;
    }
    el.innerHTML = `
      <table class="data-table w-full">
        <thead><tr>
          <th>#</th><th>Source</th><th>Date</th><th>Section</th>
          <th class="text-right">Assessment</th><th>FIR</th><th>Status</th>
        </tr></thead>
        <tbody>${rows.map((r, i) => `
          <tr>
            <td>${i + 1}</td>
            <td><span class="text-xs text-slate-500">${UI.escape(r._src)}</span></td>
            <td>${UI.date(r.case_date || r.inspection_date || r.created_at)}</td>
            <td>${UI.escape(r.section || r.dhara || "—")}</td>
            <td class="text-right font-medium">${UI.money(r.assessment_amount || r.total_assessment)}</td>
            <td>${UI.escape(r.fir_number || "—")}</td>
            <td>${UI.statusBadge(r.case_status || "—")}</td>
          </tr>`).join("")}
        </tbody>
      </table>`;
  }

  // ============================================================
  // Device rows
  // ============================================================
  function addDeviceRow(values = {}) {
    const tbody = document.getElementById("rf-devices");
    if (!tbody) return;
    const tr = document.createElement("tr");
    tr.className = "device-row";
    tr.innerHTML = `
      <td><input class="form-input dev-name" list="rf-device-list" value="${UI.escape(values.name || "")}"></td>
      <td><input class="form-input dev-load" type="number" step="0.01" value="${values.load || ""}"></td>
      <td><input class="form-input dev-factor" type="number" step="0.01" value="${values.factor || 1}"></td>
      <td><input class="form-input dev-hours" type="number" step="0.5" value="${values.hours || ""}"></td>
      <td><input class="form-input dev-days" type="number" value="${values.days || ""}"></td>
      <td class="text-right font-medium dev-units">0</td>
      <td><button class="btn btn-ghost btn-sm dev-del" title="Remove">✕</button></td>
    `;
    tbody.appendChild(tr);

    // when device name picked, autofill defaults
    tr.querySelector(".dev-name").addEventListener("change", async (e) => {
      const devs = await State.getDevices();
      const found = devs.find(d => d.device_name === e.target.value);
      if (found) {
        if (!tr.querySelector(".dev-load").value)   tr.querySelector(".dev-load").value = found.default_load || "";
        if (!tr.querySelector(".dev-factor").value || tr.querySelector(".dev-factor").value === "1")
                                                    tr.querySelector(".dev-factor").value = found.default_factor || 1;
        if (!tr.querySelector(".dev-hours").value)  tr.querySelector(".dev-hours").value = found.default_hours || "";
        if (!tr.querySelector(".dev-days").value)   tr.querySelector(".dev-days").value = found.default_days || "";
        recalcRow(tr);
        recalcTotals();
      }
    });
    ["dev-load", "dev-factor", "dev-hours", "dev-days"].forEach(c => {
      tr.querySelector("." + c).addEventListener("input", () => { recalcRow(tr); recalcTotals(); });
    });
    tr.querySelector(".dev-del").addEventListener("click", () => { tr.remove(); recalcTotals(); });
    return tr;
  }

  async function refreshDeviceDatalist(root) {
    const list = root.querySelector("#rf-device-list");
    if (!list) return;
    const devs = await State.getDevices();
    list.innerHTML = devs.map(d =>
      `<option value="${UI.escape(d.device_name)}">${UI.escape(d.category || "")}</option>`
    ).join("");
  }

  function recalcRow(tr) {
    const L = +tr.querySelector(".dev-load").value || 0;
    const F = +tr.querySelector(".dev-factor").value || 0;
    const H = +tr.querySelector(".dev-hours").value || 0;
    const D = +tr.querySelector(".dev-days").value || 0;
    const units = (L * F * H * D) / 1000;
    tr.querySelector(".dev-units").textContent = UI.number(units);
  }

  function recalcTotals() {
    let total = 0;
    document.querySelectorAll(".device-row").forEach(tr => {
      const L = +tr.querySelector(".dev-load").value || 0;
      const F = +tr.querySelector(".dev-factor").value || 0;
      const H = +tr.querySelector(".dev-hours").value || 0;
      const D = +tr.querySelector(".dev-days").value || 0;
      total += (L * F * H * D) / 1000;
    });
    document.getElementById("rf-total-units").textContent = UI.number(total);
  }

  function collectDevices() {
    const out = [];
    document.querySelectorAll(".device-row").forEach(tr => {
      const name = tr.querySelector(".dev-name").value.trim();
      const load = +tr.querySelector(".dev-load").value;
      if (!name && !load) return;       // skip empty rows
      out.push({
        name,
        load,
        factor: +tr.querySelector(".dev-factor").value || 1,
        hours:  +tr.querySelector(".dev-hours").value,
        days:   +tr.querySelector(".dev-days").value,
      });
    });
    return out;
  }

  // ============================================================
  // Calculate (live, doesn't save)
  // ============================================================
  async function recalc() {
    const devices = collectDevices();
    if (!devices.length) {
      document.getElementById("rf-calc-result").classList.add("hidden");
      return;
    }
    const $ = (id) => document.getElementById(id).value;
    const payload = {
      section: state.section,
      td_date: $("rf-td-date") || null,
      inspection_date: $("rf-inspection-date") || null,
      category:        $("rf-category"),
      connected_load_kw: parseFloat($("rf-cload")) || 0,
      multiplier:      parseFloat($("rf-multiplier")) || 2,
      less_unit:       parseFloat($("rf-less-unit")) || 0,
      ed_percent:      parseFloat($("rf-ed")) || undefined,
      days:            parseInt($("rf-days-override")) || undefined,
      devices,
    };
    try {
      const r  = await API.calculate(payload);
      state.lastCalc = r.data;
      const cload = parseFloat($("rf-cload")) || 0;
      let comp = null;
      if (cload > 0) {
        const c = await API.compounding({
          load_kw: cload,
          category: $("rf-category"),
          section: state.section,
        });
        comp = c.data;
        state.lastCompounding = comp;
      }
      renderCalcResult(state.lastCalc, comp);
    } catch (e) {
      UI.toast("Calculation failed: " + e.message, "error");
    }
  }

  function renderCalcResult(a, comp) {
    const root = document.getElementById("rf-calc-result");
    const body = document.getElementById("rf-calc-body");
    root.classList.remove("hidden");
    const f = a.fixed_charges || {};
    const en = a.energy_charges || {};
    const ed = a.electricity_duty || {};
    body.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 class="font-semibold mb-2 text-slate-800">Charges</h4>
          <table class="w-full text-sm">
            <tr><td class="py-1 text-slate-600">Section</td><td class="text-right font-medium">${a.section}</td></tr>
            <tr><td class="py-1 text-slate-600">Days</td><td class="text-right font-medium">${a.days}</td></tr>
            <tr><td class="py-1 text-slate-600">Months</td><td class="text-right font-medium">${UI.number(a.months)}</td></tr>
            <tr><td class="py-1 text-slate-600">Total Units</td><td class="text-right font-medium">${UI.number(a.total_units_after_less_unit)}</td></tr>
            <tr><td class="py-1 text-slate-600">Multiplier</td><td class="text-right font-medium">${a.multiplier}×</td></tr>
            <tr class="border-t"><td class="py-1 text-slate-600">Fixed Charges (final)</td><td class="text-right font-medium">${UI.money(f.final)}</td></tr>
            <tr><td class="py-1 text-slate-600">Energy Charges (final)</td><td class="text-right font-medium">${UI.money(en.final)}</td></tr>
            <tr><td class="py-1 text-slate-600">Electricity Duty</td><td class="text-right font-medium">${UI.money(ed.amount)}</td></tr>
            <tr class="border-t bg-emerald-50"><td class="py-2 font-bold text-emerald-900">Grand Total</td><td class="text-right text-lg font-bold text-emerald-900">${UI.money(a.grand_total)}</td></tr>
          </table>
        </div>

        <div>
          <h4 class="font-semibold mb-2 text-slate-800">Slab-wise Energy</h4>
          <table class="w-full text-sm">
            <thead class="text-slate-500 text-xs">
              <tr><th class="text-left pb-1">Slab</th><th class="text-right pb-1">Units</th>
                  <th class="text-right pb-1">Rate</th><th class="text-right pb-1">Amount</th></tr>
            </thead>
            <tbody>${(en.slabs || []).map(s => `
              <tr>
                <td>${s.slab_start}-${s.slab_end ?? "∞"}</td>
                <td class="text-right">${UI.number(s.yearly_units)}</td>
                <td class="text-right">₹${s.rate}</td>
                <td class="text-right font-medium">${UI.money(s.amount)}</td>
              </tr>`).join("")}
            </tbody>
          </table>

          ${comp ? `
            <h4 class="font-semibold mt-5 mb-2 text-slate-800">Section 152 Compounding</h4>
            <table class="w-full text-sm">
              <tr><td class="py-1">Load</td><td class="text-right">${comp.load_w} W (${comp.load_kw} KW)</td></tr>
              <tr><td class="py-1">Billable KW <span class="text-xs text-slate-500">(per KW or part thereof)</span></td>
                  <td class="text-right font-medium">${comp.billable_kw} KW</td></tr>
              <tr><td class="py-1">Rate per KW</td><td class="text-right">${UI.money(comp.rate_per_kw)}</td></tr>
              <tr class="border-t bg-amber-50"><td class="py-2 font-bold text-amber-900">Compounding Amount</td>
                  <td class="text-right text-lg font-bold text-amber-900">${UI.money(comp.compounding_amount)}</td></tr>
            </table>
            <details class="mt-2 text-xs text-slate-500">
              <summary class="cursor-pointer">📜 Justification text</summary>
              <p class="mt-2 leading-relaxed font-hindi">${UI.escape(comp.justification_hi)}</p>
            </details>
          ` : ""}
        </div>
      </div>

      ${(a.warnings || []).length ? `
        <div class="mt-4 bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-800">
          ${a.warnings.map(w => `• ${UI.escape(w)}`).join("<br>")}
        </div>` : ""}
    `;

    // Update save bar
    document.getElementById("save-total").textContent = UI.money(a.grand_total);
    document.getElementById("save-compounding").textContent = comp ? UI.money(comp.compounding_amount) : "—";
  }

  // ============================================================
  // Save
  // ============================================================
  async function saveCase() {
    const $ = (id) => document.getElementById(id).value;
    const account = $("rf-account").trim();
    if (!account) { UI.toast("Account number is required.", "warn"); return; }
    const devices = collectDevices();
    if (!devices.length) { UI.toast("Add at least one device.", "warn"); return; }

    if (!state.lastCalc) await recalc();

    const body = {
      account_number: account,
      name: $("rf-name"), father_name: $("rf-father"),
      mobile: $("rf-mobile"), village: $("rf-village"),
      post_office: $("rf-post"), pin_code: $("rf-pin"),
      category: $("rf-category") || "LMV-1",
      section: state.section,
      section_other: state.section === "Other" ? $("rf-section-other-input") : null,
      td_date: $("rf-td-date") || null,
      inspection_date: $("rf-inspection-date") || null,
      checking_type: $("rf-checking"),
      je_name: $("rf-je"),
      sub_substation: $("rf-substation"),
      online_no: $("rf-online"),
      fir_number: $("rf-fir"),
      connected_load_kw: parseFloat($("rf-cload")) || 0,
      less_unit: parseFloat($("rf-less-unit")) || 0,
      multiplier: parseFloat($("rf-multiplier")) || 2,
      offense_count: state.offenseCount + 1,
      devices,
      assessment: state.lastCalc,
      total_assessment: state.lastCalc?.grand_total,
      compounding_amount: state.lastCompounding?.compounding_amount,
      calculate_compounding: !state.lastCompounding,
      created_by: "web-ui",
    };

    state.saving = true;
    try {
      UI.toast("Saving case…", "info", 1500);
      const r = await API.saveCase(body);
      const cid = r.data.case.case_id;
      UI.toast(`Case saved: ${cid}`, "success");
      // Navigate to the new case
      window.location.hash = `#/case/${encodeURIComponent(cid)}`;
    } catch (e) {
      UI.toast("Save failed: " + e.message, "error");
    } finally {
      state.saving = false;
    }
  }

  return { render };
})();
