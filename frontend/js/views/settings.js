/* =====================================================================
   views/settings.js — view + edit system config (office identity, business rules)
   ===================================================================== */

const SettingsView = (function () {

  // Office identity keys (editable as a single form)
  const OFFICE_KEYS = [
    ["office_phone",                 "Phone / फोन",                   "tel"],
    ["office_email",                 "Email / ईमेल",                  "email"],
    ["office_division_no",           "Division No. / डिवीजन नं.",       "text"],
    ["office_name_hi",               "Office Name (Hindi)",            "text"],
    ["office_name_en",               "Office Name (English)",          "text"],
    ["office_dept_hi",               "Department (Hindi)",             "text"],
    ["office_dept_en",               "Department (English)",           "text"],
    ["office_location_hi",           "Location (Hindi)",               "text"],
    ["office_location_en",           "Location (English)",             "text"],
    ["patrank_letter_code",          "पत्रांक Letter Code",            "text"],
    ["hearing_officer_address_hi",   "Hearing Officer Address (Hindi)", "text"],
  ];

  const BUSINESS_KEYS = [
    ["multiplier_first_offense",      "First Offense Multiplier"],
    ["multiplier_repeat_offense",     "Repeat Offense Multiplier"],
    ["repeat_offense_threshold",      "Repeat Threshold (cases)"],
    ["default_days_section_135",      "Default Days (Sec 135)"],
    ["admin_fee_section_3",           "Admin Fee (Sec 3) ₹"],
    ["timeline_provisional_payment",  "Provisional Payment Days"],
    ["timeline_appeal_window",        "Appeal Window Days"],
    ["timeline_section_3_dispatch",   "Sec 3 Dispatch Deadline (days)"],
    ["timeline_section_5_dispatch",   "Sec 5 Dispatch Deadline (days)"],
    ["ed_default_percent",            "Default ED %"],
  ];

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-4">
        <!-- ====== Office Identity (editable) ====== -->
        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>🏢 Office Identity / कार्यालय पहचान</span>
            <span class="text-xs text-slate-500">Used in provisional notice header</span>
          </div>
          <div id="st-office" class="card-body">${UI.spinner()}</div>
        </div>

        <!-- ====== Business Rules (editable) ====== -->
        <div class="card">
          <div class="card-header">⚙️ Business Rules / व्यवसाय नियम</div>
          <div id="st-business" class="card-body">${UI.spinner()}</div>
        </div>

        <!-- ====== Server Health ====== -->
        <div class="card">
          <div class="card-header">🩺 Server Health</div>
          <div id="st-health" class="card-body">${UI.spinner()}</div>
        </div>

        <!-- ====== Document Templates ====== -->
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

    paintOffice(document.getElementById("st-office"), cfg);
    paintBusiness(document.getElementById("st-business"), cfg);
    paintHealth(document.getElementById("st-health"), hp);
    paintTemplates(document.getElementById("st-templates"), dk);
  }

  // ============================================================
  function paintOffice(el, settled) {
    if (settled.status !== "fulfilled") {
      el.innerHTML = UI.errorBox(settled.reason); return;
    }
    const cfg = settled.value.data || {};
    el.innerHTML = `
      <p class="text-sm text-slate-600 mb-3">
        Yeh details provisional notice ke header me appear honge.
        Apne division ka data fill kar lo aur Save dabao.
      </p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        ${OFFICE_KEYS.map(([k, label, type]) => `
          <div>
            <label class="form-label">${UI.escape(label)}</label>
            <input id="off-${k}" type="${type}" class="form-input"
                   value="${UI.escape(cfg[k] || '')}"
                   data-config-key="${k}" />
          </div>`).join("")}
      </div>
      <div class="flex gap-2">
        <button id="st-office-save" class="btn btn-primary">💾 Save Office Settings</button>
        <span id="st-office-status" class="text-sm text-slate-500 self-center"></span>
      </div>`;

    document.getElementById("st-office-save").addEventListener("click", async () => {
      const updates = {};
      for (const [k] of OFFICE_KEYS) {
        const inp = document.getElementById(`off-${k}`);
        if (inp) updates[k] = inp.value;
      }
      const status = document.getElementById("st-office-status");
      status.textContent = "Saving…";
      try {
        await API.request("/api/system/config", { method: "POST", body: { updates } });
        status.textContent = "✅ Saved!";
        UI.toast("Office settings updated", "success");
        setTimeout(() => { status.textContent = ""; }, 3000);
      } catch (e) {
        status.textContent = "";
        UI.toast(e.message, "error");
      }
    });
  }

  // ============================================================
  function paintBusiness(el, settled) {
    if (settled.status !== "fulfilled") {
      el.innerHTML = UI.errorBox(settled.reason); return;
    }
    const cfg = settled.value.data || {};
    el.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        ${BUSINESS_KEYS.map(([k, label]) => `
          <div>
            <label class="form-label">${UI.escape(label)}</label>
            <input id="bz-${k}" type="number" step="0.5" class="form-input"
                   value="${UI.escape(cfg[k] || '')}" />
          </div>`).join("")}
      </div>
      <div class="flex gap-2">
        <button id="st-business-save" class="btn btn-primary">💾 Save Business Rules</button>
        <span id="st-business-status" class="text-sm text-slate-500 self-center"></span>
      </div>`;

    document.getElementById("st-business-save").addEventListener("click", async () => {
      const updates = {};
      for (const [k] of BUSINESS_KEYS) {
        const inp = document.getElementById(`bz-${k}`);
        if (inp && inp.value !== "") updates[k] = inp.value;
      }
      const status = document.getElementById("st-business-status");
      status.textContent = "Saving…";
      try {
        await API.request("/api/system/config", { method: "POST", body: { updates } });
        status.textContent = "✅ Saved!";
        UI.toast("Business rules updated", "success");
        setTimeout(() => { status.textContent = ""; }, 3000);
      } catch (e) {
        status.textContent = "";
        UI.toast(e.message, "error");
      }
    });
  }

  // ============================================================
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
