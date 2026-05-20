/* =====================================================================
   views/case-detail.js — full case view with tabs:
     Overview / Devices+Assessment / Payments / Inquiries / Notices /
     Documents / Revisions
   ===================================================================== */

const CaseDetailView = (function () {

  const state = { caseId: null, full: null, currentTab: "overview" };

  async function render(root, params) {
    state.caseId = params.id;
    state.currentTab = "overview";
    root.innerHTML = UI.spinner("Loading case…");

    try {
      const r = await API.getCase(state.caseId);
      state.full = r.data;
      paint(root);
    } catch (e) {
      root.innerHTML = UI.errorBox(e);
    }
  }

  function paint(root) {
    const f = state.full;
    const c = f.case;
    const cons = f.consumer || {};
    const tl = f.timeline || {};

    root.innerHTML = `
      <div class="space-y-4">

        <!-- Header bar -->
        <div class="card">
          <div class="card-body flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-3 flex-wrap">
                <h2 class="text-xl font-bold text-slate-900 font-mono">${UI.escape(c.case_id)}</h2>
                ${UI.statusBadge(c.case_status)}
                ${c.section ? `<span class="text-xs px-2 py-1 bg-slate-100 rounded">Section ${UI.escape(c.section)}</span>` : ""}
              </div>
              <p class="text-sm text-slate-600 mt-1">
                ${UI.escape(cons.name || c.user_name || "—")}
                ${cons.father_name ? `S/o ${UI.escape(cons.father_name)}` : ""}
                · <span class="font-mono">${UI.escape(c.account_number || "—")}</span>
                · ${UI.escape(cons.village || "—")}
              </p>
              <p class="text-xs text-slate-500 mt-1">
                Inspection: ${UI.date(c.inspection_date)} · J.E.: ${UI.escape(c.je_name || "—")} · Online: ${UI.escape(c.online_no || "—")}
              </p>
            </div>

            <div class="text-right">
              <div class="text-xs text-slate-500">Assessment</div>
              <div class="text-2xl font-bold text-slate-800">${UI.money(c.total_assessment)}</div>
              <div class="text-xs text-slate-500 mt-1">+ Compounding ${UI.money(c.compounding_amount)}</div>
            </div>
          </div>

          ${tl.elapsed_days != null ? `
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 px-4 pb-4 text-xs">
            ${tlBlock("Elapsed", `${tl.elapsed_days} days`, "bg-slate-100")}
            ${tlBlock("Provisional Pay Due", UI.date(tl.provisional_payment_due),
                     tl.elapsed_days > 7 ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800")}
            ${tlBlock("Appeal Window Closes", UI.date(tl.appeal_window_close), "bg-blue-100 text-blue-800")}
            ${tlBlock("Sec 3 Due", UI.date(tl.section3_dispatch_due),
                     tl.overdue_section3 ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800")}
            ${tlBlock("Sec 5 Due", UI.date(tl.section5_dispatch_due),
                     tl.overdue_section5 ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800")}
          </div>` : ""}
        </div>

        <!-- Tab strip -->
        <div class="card">
          <div class="border-b border-slate-200 px-2 flex flex-wrap">
            ${tab("overview",   "Overview")}
            ${tab("assessment", "Assessment & Devices")}
            ${tab("payments",   "Payments")}
            ${tab("inquiries",  "Inquiries")}
            ${tab("notices",    "Notices")}
            ${tab("documents",  "Documents")}
            ${tab("revisions",  "Revisions")}
          </div>
          <div id="cd-tab-body" class="card-body"></div>
        </div>
      </div>`;

    document.querySelectorAll("[data-tab]").forEach(b => {
      b.addEventListener("click", () => switchTab(b.dataset.tab));
    });
    switchTab("overview");
  }

  function tab(key, label) {
    return `<button data-tab="${key}" class="tab-btn">${label}</button>`;
  }
  function tlBlock(label, val, cls) {
    return `<div class="${cls} rounded px-2 py-1.5">
              <div class="text-[10px] uppercase tracking-wide opacity-75">${label}</div>
              <div class="font-medium">${UI.escape(val || "—")}</div>
            </div>`;
  }

  function switchTab(key) {
    state.currentTab = key;
    document.querySelectorAll("[data-tab]").forEach(b => {
      b.classList.toggle("active", b.dataset.tab === key);
    });
    const body = document.getElementById("cd-tab-body");
    const fns = {
      overview:   tabOverview,
      assessment: tabAssessment,
      payments:   tabPayments,
      inquiries:  tabInquiries,
      notices:    tabNotices,
      documents:  tabDocuments,
      revisions:  tabRevisions,
    };
    body.innerHTML = (fns[key] || (() => "—"))();

    // bind handlers per tab
    if (key === "payments")  bindPayments();
    if (key === "inquiries") bindInquiries();
    if (key === "notices")   bindNotices();
    if (key === "documents") bindDocuments();
    if (key === "assessment") bindAssessment();
  }

  // ============================================================ tab: overview
  function tabOverview() {
    const f = state.full;
    const cons = f.consumer || {};
    const c = f.case;
    return `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${kvCard("उपभोक्ता / Consumer", [
          ["Account No.",  c.account_number],
          ["Name",         cons.name],
          ["Father",       cons.father_name],
          ["Mobile",       cons.mobile],
          ["Village",      cons.village],
          ["Post",         cons.post_office],
          ["Pin",          cons.pin_code],
          ["Tehsil",       cons.tehsil],
          ["District",     cons.district],
          ["Category",     cons.category],
          ["Supply Type",  cons.supply_type],
          ["Connected Load", cons.load_value],
        ])}
        ${kvCard("Case Details", [
          ["Section",        c.section],
          ["Other Section",  c.section_other],
          ["TD Date",        UI.date(c.td_date)],
          ["Inspection",     UI.date(c.inspection_date)],
          ["Checking Type",  c.checking_type],
          ["JE Name",        c.je_name],
          ["Sub-Substation", c.sub_substation],
          ["FIR Number",     c.fir_number],
          ["Online No.",     c.online_no],
          ["Multiplier",     c.multiplier ? `${c.multiplier}×` : "—"],
          ["Offense #",      c.offense_count],
          ["Created",        UI.dateTime(c.created_at)],
        ])}
      </div>`;
  }

  function kvCard(title, rows) {
    return `<div class="border border-slate-200 rounded-lg overflow-hidden">
      <div class="bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">${UI.escape(title)}</div>
      <table class="w-full text-sm">
        ${rows.map(([k,v]) => `
          <tr class="border-b border-slate-100 last:border-0">
            <td class="py-1.5 px-3 text-slate-500 w-1/2">${UI.escape(k)}</td>
            <td class="py-1.5 px-3 font-medium">${UI.escape(v ?? "—")}</td>
          </tr>`).join("")}
      </table>
    </div>`;
  }

  // ============================================================ tab: assessment
  function tabAssessment() {
    const c = state.full.case;
    const a = c.assessment;
    if (!a) {
      return `<p class="text-sm text-slate-500">No assessment yet — click <button id="cd-recalc" class="btn btn-primary btn-sm">Recalculate</button></p>`;
    }
    const f = a.fixed_charges || {}, en = a.energy_charges || {}, ed = a.electricity_duty || {};
    const devs = a.devices || c.devices || [];
    return `
      <div class="space-y-4">
        <div class="flex justify-between items-center">
          <h4 class="font-semibold">Devices (${devs.length})</h4>
          <button id="cd-recalc" class="btn btn-secondary btn-sm">🧮 Recalculate</button>
        </div>
        <table class="data-table w-full">
          <thead><tr><th>#</th><th>Device</th><th class="text-right">L (W)</th><th class="text-right">F</th>
                     <th class="text-right">H</th><th class="text-right">D</th><th class="text-right">Units</th></tr></thead>
          <tbody>${devs.map((d,i) => `
            <tr><td>${i+1}</td><td>${UI.escape(d.name||"")}</td>
              <td class="text-right">${UI.number(d.L||d.load)}</td>
              <td class="text-right">${UI.number(d.F||d.factor)}</td>
              <td class="text-right">${UI.number(d.H||d.hours)}</td>
              <td class="text-right">${UI.number(d.D||d.days)}</td>
              <td class="text-right font-medium">${UI.number(d.units)}</td>
            </tr>`).join("")}</tbody>
        </table>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="border border-slate-200 rounded p-4">
            <h5 class="font-semibold mb-2">Charges Summary</h5>
            <table class="w-full text-sm">
              <tr><td class="py-1">Days</td><td class="text-right">${a.days}</td></tr>
              <tr><td class="py-1">Multiplier</td><td class="text-right">${a.multiplier}×</td></tr>
              <tr><td class="py-1">Total Units</td><td class="text-right">${UI.number(a.total_units_after_less_unit)}</td></tr>
              <tr class="border-t"><td class="py-1.5">Fixed (final)</td><td class="text-right">${UI.money(f.final)}</td></tr>
              <tr><td class="py-1.5">Energy (final)</td><td class="text-right">${UI.money(en.final)}</td></tr>
              <tr><td class="py-1.5">Electricity Duty</td><td class="text-right">${UI.money(ed.amount)}</td></tr>
              <tr class="border-t bg-emerald-50"><td class="py-2 font-bold">Grand Total</td>
                  <td class="text-right text-lg font-bold">${UI.money(a.grand_total)}</td></tr>
            </table>
          </div>

          <div class="border border-slate-200 rounded p-4">
            <h5 class="font-semibold mb-2">Slab Breakdown</h5>
            <table class="w-full text-sm">
              <thead><tr class="text-xs text-slate-500"><th class="text-left pb-1">Slab</th>
                <th class="text-right pb-1">Units</th>
                <th class="text-right pb-1">Rate</th>
                <th class="text-right pb-1">Amount</th></tr></thead>
              <tbody>${(en.slabs||[]).map(s => `
                <tr><td>${s.slab_start}-${s.slab_end ?? "∞"}</td>
                    <td class="text-right">${UI.number(s.yearly_units)}</td>
                    <td class="text-right">₹${s.rate}</td>
                    <td class="text-right">${UI.money(s.amount)}</td></tr>`).join("")}</tbody>
            </table>
          </div>
        </div>
      </div>`;
  }

  function bindAssessment() {
    const btn = document.getElementById("cd-recalc");
    if (btn) btn.addEventListener("click", async () => {
      try {
        UI.toast("Recalculating…", "info");
        await API.caseCalculate(state.caseId, {});
        const r = await API.getCase(state.caseId);
        state.full = r.data;
        switchTab("assessment");
        UI.toast("Updated.", "success");
      } catch (e) { UI.toast(e.message, "error"); }
    });
  }

  // ============================================================ tab: payments
  function tabPayments() {
    const c = state.full.case;
    const payments = state.full.payments || [];
    const totalPaid = payments.reduce((s,p) => s + (+p.amount || 0), 0);
    const due = (+c.total_assessment || 0) + (+c.compounding_amount || 0);
    const balance = due - totalPaid;

    return `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div class="bg-slate-50 rounded p-3">
          <div class="text-xs text-slate-500">Total Due</div>
          <div class="text-xl font-bold">${UI.money(due)}</div>
        </div>
        <div class="bg-emerald-50 rounded p-3">
          <div class="text-xs text-emerald-700">Total Paid</div>
          <div class="text-xl font-bold text-emerald-800">${UI.money(totalPaid)}</div>
        </div>
        <div class="${balance <= 0 ? 'bg-emerald-50' : 'bg-red-50'} rounded p-3">
          <div class="text-xs ${balance <= 0 ? 'text-emerald-700' : 'text-red-700'}">Balance</div>
          <div class="text-xl font-bold ${balance <= 0 ? 'text-emerald-800' : 'text-red-800'}">${UI.money(balance)}</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-6 gap-2 mb-4 p-3 bg-slate-50 rounded border border-slate-200">
        <input id="pay-amount" type="number" class="form-input md:col-span-1" placeholder="Amount" />
        <select id="pay-component" class="form-select md:col-span-1">
          <option value="assessment">Assessment</option>
          <option value="compounding">Compounding</option>
          <option value="shaman">Shaman</option>
          <option value="admin">Admin</option>
        </select>
        <select id="pay-type" class="form-select md:col-span-1">
          <option value="full">Full</option>
          <option value="partial" selected>Partial</option>
          <option value="installment">Installment</option>
        </select>
        <input id="pay-receipt" class="form-input md:col-span-1" placeholder="Receipt #" />
        <input id="pay-date" type="date" class="form-input md:col-span-1" />
        <button id="pay-save" class="btn btn-success md:col-span-1">＋ Record</button>
      </div>

      <table class="data-table w-full">
        <thead><tr>
          <th>Date</th><th>Receipt</th><th>Component</th><th>Type</th>
          <th class="text-right">Amount</th><th>Method</th><th>Remarks</th><th></th>
        </tr></thead>
        <tbody>${payments.length ? payments.map(p => `
          <tr>
            <td>${UI.date(p.payment_date)}</td>
            <td class="font-mono text-xs">${UI.escape(p.receipt_number || "—")}</td>
            <td>${UI.escape(p.component || "—")}</td>
            <td>${UI.escape(p.payment_type || "—")}</td>
            <td class="text-right font-medium">${UI.money(p.amount)}</td>
            <td>${UI.escape(p.payment_method || "—")}</td>
            <td class="text-xs text-slate-500">${UI.escape(p.remarks || "")}</td>
            <td><button class="btn btn-ghost btn-sm" data-pay-del="${p.id}">🗑️</button></td>
          </tr>`).join("") : `<tr><td colspan="8" class="text-center py-6 text-slate-400">No payments recorded.</td></tr>`}
        </tbody>
      </table>`;
  }

  function bindPayments() {
    const def = document.getElementById("pay-date");
    if (def && !def.value) def.value = new Date().toISOString().slice(0, 10);

    document.getElementById("pay-save").addEventListener("click", async () => {
      const amt = parseFloat(document.getElementById("pay-amount").value);
      if (!amt || amt <= 0) { UI.toast("Enter amount > 0", "warn"); return; }
      try {
        await API.recordPayment(state.caseId, {
          amount: amt,
          component: document.getElementById("pay-component").value,
          payment_type: document.getElementById("pay-type").value,
          receipt_number: document.getElementById("pay-receipt").value,
          payment_date: document.getElementById("pay-date").value,
          payment_method: "cash",
        });
        UI.toast("Payment recorded.", "success");
        await refresh();
      } catch (e) { UI.toast(e.message, "error"); }
    });

    document.querySelectorAll("[data-pay-del]").forEach(b => {
      b.addEventListener("click", async () => {
        if (!await UI.confirm("Reverse this payment?", { danger: true })) return;
        try {
          await API.deletePayment(b.dataset.payDel);
          UI.toast("Reversed.", "success");
          await refresh();
        } catch (e) { UI.toast(e.message, "error"); }
      });
    });
  }

  // ============================================================ tab: inquiries
  function tabInquiries() {
    const items = state.full.inquiries || [];
    return `
      <div class="grid grid-cols-1 md:grid-cols-6 gap-2 mb-4 p-3 bg-slate-50 rounded border border-slate-200">
        <input id="inq-name" class="form-input md:col-span-1" placeholder="Caller name" />
        <input id="inq-mobile" class="form-input md:col-span-1" placeholder="Mobile" />
        <select id="inq-rel" class="form-select md:col-span-1">
          <option value="self">Self</option>
          <option value="relative">Relative</option>
          <option value="advocate">Advocate</option>
          <option value="other">Other</option>
        </select>
        <input id="inq-amt" type="number" class="form-input md:col-span-1" placeholder="Amount quoted" />
        <input id="inq-remarks" class="form-input md:col-span-1" placeholder="Remarks" />
        <button id="inq-save" class="btn btn-primary md:col-span-1">＋ Log</button>
      </div>

      <table class="data-table w-full">
        <thead><tr>
          <th>Date</th><th>Caller</th><th>Mobile</th><th>Relation</th>
          <th class="text-right">Quoted</th><th>Remarks</th>
        </tr></thead>
        <tbody>${items.length ? items.map(q => `
          <tr>
            <td class="text-xs text-slate-500">${UI.dateTime(q.inquiry_date)}</td>
            <td class="font-medium">${UI.escape(q.caller_name)}</td>
            <td>${UI.escape(q.mobile_number || "—")}</td>
            <td>${UI.escape(q.relationship || "—")}</td>
            <td class="text-right">${UI.money(q.amount_quoted)}</td>
            <td class="text-xs text-slate-500">${UI.escape(q.remarks || "")}</td>
          </tr>`).join("") : `<tr><td colspan="6" class="text-center py-6 text-slate-400">No inquiries logged.</td></tr>`}
        </tbody>
      </table>`;
  }

  function bindInquiries() {
    document.getElementById("inq-save").addEventListener("click", async () => {
      const body = {
        caller_name: document.getElementById("inq-name").value.trim(),
        mobile_number: document.getElementById("inq-mobile").value,
        relationship: document.getElementById("inq-rel").value,
        amount_quoted: parseFloat(document.getElementById("inq-amt").value) || null,
        remarks: document.getElementById("inq-remarks").value,
      };
      if (!body.caller_name) { UI.toast("Caller name required", "warn"); return; }
      try {
        await API.addInquiry(state.caseId, body);
        UI.toast("Inquiry logged.", "success");
        await refresh();
      } catch (e) { UI.toast(e.message, "error"); }
    });
  }

  // ============================================================ tab: notices
  function tabNotices() {
    const items = state.full.notices || [];
    return `
      <div class="grid grid-cols-1 md:grid-cols-6 gap-2 mb-4 p-3 bg-slate-50 rounded border border-slate-200">
        <select id="nt-type" class="form-select md:col-span-1">
          <option value="provisional">Provisional</option>
          <option value="section3">Section 3</option>
          <option value="section5">Section 5</option>
          <option value="thanedari">Thanedari</option>
          <option value="deposit_slip">Deposit Slip</option>
          <option value="noc">NOC</option>
        </select>
        <input id="nt-no"      class="form-input md:col-span-1" placeholder="Notice No." />
        <input id="nt-dispatch" type="date" class="form-input md:col-span-1" />
        <input id="nt-due"      type="date" class="form-input md:col-span-1" />
        <input id="nt-amt"      type="number" class="form-input md:col-span-1" placeholder="Amount (auto)" />
        <button id="nt-save" class="btn btn-primary md:col-span-1">＋ Add</button>
      </div>

      <table class="data-table w-full">
        <thead><tr>
          <th>Type</th><th>Notice No.</th><th>Dispatch</th><th>Due</th>
          <th class="text-right">Amount</th><th>Status</th>
        </tr></thead>
        <tbody>${items.length ? items.map(n => `
          <tr>
            <td class="font-medium">${UI.escape(n.notice_type)}</td>
            <td class="font-mono text-xs">${UI.escape(n.notice_number || "—")}</td>
            <td>${UI.date(n.dispatch_date)}</td>
            <td>${UI.date(n.due_date)}</td>
            <td class="text-right">${UI.money(n.amount)}</td>
            <td>${UI.statusBadge(n.status)}</td>
          </tr>`).join("") : `<tr><td colspan="6" class="text-center py-6 text-slate-400">No notices yet.</td></tr>`}
        </tbody>
      </table>`;
  }

  function bindNotices() {
    document.getElementById("nt-save").addEventListener("click", async () => {
      const body = {
        notice_type: document.getElementById("nt-type").value,
        notice_number: document.getElementById("nt-no").value || undefined,
        dispatch_date: document.getElementById("nt-dispatch").value || undefined,
        due_date: document.getElementById("nt-due").value || undefined,
        amount: parseFloat(document.getElementById("nt-amt").value) || undefined,
      };
      try {
        await API.addNotice(state.caseId, body);
        UI.toast("Notice added.", "success");
        await refresh();
      } catch (e) { UI.toast(e.message, "error"); }
    });
  }

  // ============================================================ tab: documents
  function tabDocuments() {
    const docs = state.full.documents || [];
    const kinds = [
      ["provisional_consumer", "Provisional (Consumer Copy)"],
      ["provisional_office",   "Provisional (Office Copy)"],
      ["section3",             "Section 3 Notice"],
      ["section5",             "Section 5 Notice"],
      ["thanedari",            "Thanedari Copy"],
      ["envelope",             "Envelope"],
      ["deposit_slip",         "Deposit Slip"],
      ["compounding_order",    "Compounding Order"],
      ["noc",                  "NOC"],
    ];
    return `
      <div class="mb-4 p-3 bg-slate-50 rounded border border-slate-200">
        <h4 class="font-semibold text-sm mb-2">Generate Document</h4>
        <div class="flex flex-wrap gap-2">
          ${kinds.map(([k, label]) => `
            <button class="btn btn-secondary btn-sm" data-gen="${k}">📄 ${UI.escape(label)}</button>
          `).join("")}
        </div>
      </div>

      <table class="data-table w-full">
        <thead><tr>
          <th>Generated</th><th>Type</th><th>File</th><th>Size</th><th></th>
        </tr></thead>
        <tbody>${docs.length ? docs.map(d => `
          <tr>
            <td class="text-xs text-slate-500">${UI.dateTime(d.created_at)}</td>
            <td>${UI.escape(d.document_type)}</td>
            <td class="font-mono text-xs">${UI.escape(d.document_name)}</td>
            <td class="text-xs">${UI.number((d.file_size||0)/1024)} KB</td>
            <td><a class="btn btn-ghost btn-sm" href="${API.documentDownloadUrl(d.id)}" target="_blank">⬇ Download</a></td>
          </tr>`).join("") : `<tr><td colspan="5" class="text-center py-6 text-slate-400">No documents generated yet.</td></tr>`}
        </tbody>
      </table>`;
  }

  function bindDocuments() {
    document.querySelectorAll("[data-gen]").forEach(b => {
      b.addEventListener("click", async () => {
        const kind = b.dataset.gen;
        try {
          UI.toast(`Generating ${kind}…`, "info");
          const r = await API.generateDocument(state.caseId, kind);
          UI.toast("Generated.", "success");
          // Open download in new tab
          window.open(API.documentDownloadUrl(r.data.id), "_blank");
          await refresh();
        } catch (e) { UI.toast(e.message, "error"); }
      });
    });
  }

  // ============================================================ tab: revisions
  function tabRevisions() {
    const items = state.full.revisions || [];
    return items.length ? `
      <table class="data-table w-full">
        <thead><tr>
          <th>Rev #</th><th>Reason</th><th>By</th><th>When</th>
          <th class="text-right">Original</th><th class="text-right">Revised</th><th>Approval</th>
        </tr></thead>
        <tbody>${items.map(r => `
          <tr>
            <td class="font-bold">${r.revision_number}</td>
            <td>${UI.escape(r.revision_reason)}</td>
            <td>${UI.escape(r.revised_by)}</td>
            <td class="text-xs">${UI.dateTime(r.revised_at)}</td>
            <td class="text-right">${UI.money(r.original_assessment)}</td>
            <td class="text-right font-medium">${UI.money(r.revised_assessment)}</td>
            <td>${UI.statusBadge(r.approval_status)}</td>
          </tr>`).join("")}
        </tbody>
      </table>` : UI.empty("No revisions yet.");
  }

  // -- helpers
  async function refresh() {
    const r = await API.getCase(state.caseId);
    state.full = r.data;
    switchTab(state.currentTab);
  }

  return { render };
})();
