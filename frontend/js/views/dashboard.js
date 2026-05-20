/* =====================================================================
   views/dashboard.js — overview stats + timeline alerts + recent items
   ===================================================================== */

const DashboardView = (function () {

  async function render(root) {
    root.innerHTML = `
      <div class="space-y-6">
        <!-- Stat cards -->
        <div id="dash-stats" class="grid grid-cols-2 md:grid-cols-4 gap-4"></div>

        <!-- Timeline alerts -->
        <div class="card">
          <div class="card-header flex items-center justify-between">
            <span>⏰ Timeline Alerts</span>
            <span class="text-xs text-slate-500">Legal compliance deadlines</span>
          </div>
          <div id="dash-alerts" class="card-body">
            <p class="text-sm text-slate-500">Loading alerts…</p>
          </div>
        </div>

        <!-- Recent activity grid -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="card">
            <div class="card-header">💰 Recent Payments</div>
            <div id="dash-payments" class="card-body p-0"><p class="p-4 text-sm text-slate-400">Loading…</p></div>
          </div>
          <div class="card">
            <div class="card-header">📞 Recent Inquiries</div>
            <div id="dash-inquiries" class="card-body p-0"><p class="p-4 text-sm text-slate-400">Loading…</p></div>
          </div>
        </div>
      </div>`;

    // Fire all in parallel — each one independently updates its section
    try {
      const [summary, alerts, payments, inquiries] = await Promise.allSettled([
        API.dashboardSummary(),
        API.timelineAlerts(),
        API.recentPayments(8),
        API.recentInquiries(8),
      ]);
      renderStats(document.getElementById("dash-stats"), summary);
      renderAlerts(document.getElementById("dash-alerts"), alerts);
      renderPayments(document.getElementById("dash-payments"), payments);
      renderInquiries(document.getElementById("dash-inquiries"), inquiries);
    } catch (e) {
      console.error("Dashboard load error:", e);
      document.getElementById("dash-stats").innerHTML = UI.errorBox(
        "Backend server se connect nahi ho paa raha. Kya python -m backend.app chal raha hai? Check karo http://localhost:5000/api/health"
      );
    }
  }

  // ---------------------------------------------- stat cards
  function renderStats(el, settled) {
    if (settled.status !== "fulfilled") {
      el.innerHTML = UI.errorBox(settled.reason);
      return;
    }
    const d = settled.value.data || {};
    const cards = [
      { label: "Total Cases",        value: UI.number(d.total_cases),
        sub: "All cases",            color: "bg-brand-600" },
      { label: "Total Assessment",   value: UI.money(d.total_assessment),
        sub: "Lifetime",              color: "bg-emerald-600" },
      { label: "Today's Collection", value: UI.money(d.today_payment_amount),
        sub: `${d.today_payment_count || 0} receipts`, color: "bg-violet-600" },
      { label: "Open / Pending",
        value: UI.number((d.by_status?.open?.count || 0) + (d.by_status?.noticed?.count || 0)),
        sub: "Awaiting closure",     color: "bg-amber-500" },
    ];
    el.innerHTML = cards.map(c => `
      <div class="stat-card card p-4">
        <div class="flex items-start justify-between">
          <div>
            <div class="text-xs uppercase tracking-wide text-slate-500">${c.label}</div>
            <div class="text-2xl font-bold mt-1 text-slate-800">${c.value}</div>
            <div class="text-xs text-slate-400 mt-1">${c.sub}</div>
          </div>
          <div class="${c.color} w-10 h-10 rounded-lg opacity-90"></div>
        </div>
      </div>`).join("");
  }

  // ---------------------------------------------- timeline alerts
  function renderAlerts(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const d = settled.value.data || {};
    const blocks = [
      { key: "section3_due",        label: "Section 3 Notice Due (>45 days)", colour: "bg-amber-100 text-amber-800",
        items: d.section3_due || [], count: d.section3_due_count || 0 },
      { key: "section5_due",        label: "Section 5 Notice Due (>90 days)", colour: "bg-red-100 text-red-800",
        items: d.section5_due || [], count: d.section5_due_count || 0 },
      { key: "provisional_overdue", label: "Provisional Payment Overdue (>7d)", colour: "bg-red-100 text-red-800",
        items: d.provisional_overdue || [], count: d.provisional_overdue_count || 0 },
      { key: "appeal_window_open",  label: "Appeal Window Open (<15 days)", colour: "bg-blue-100 text-blue-800",
        items: d.appeal_window_open || [], count: d.appeal_window_open_count || 0 },
    ];
    if (blocks.every(b => b.count === 0)) {
      el.innerHTML = `<p class="text-sm text-slate-500">✅ Sab kuch on track — no overdue items.</p>`;
      return;
    }
    el.innerHTML = blocks.map(b => `
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2">
          <span class="px-2 py-1 rounded text-xs font-semibold ${b.colour}">${b.label}</span>
          <span class="text-sm font-bold text-slate-700">${b.count}</span>
        </div>
        ${b.count === 0 ? '<p class="text-xs text-slate-400 ml-1">None.</p>' : `
          <ul class="text-sm divide-y divide-slate-100 border border-slate-200 rounded">
            ${b.items.slice(0,5).map(c => `
              <li class="flex items-center justify-between px-3 py-2">
                <a href="#/case/${encodeURIComponent(c.case_id)}" class="text-brand-700 hover:underline">${UI.escape(c.case_id)}</a>
                <span class="text-slate-500 text-xs">${UI.escape(c.user_name||"")} • ${UI.date(c.inspection_date)}</span>
                <span class="font-medium">${UI.money(c.total_assessment)}</span>
              </li>`).join("")}
          </ul>
          ${b.count > 5 ? `<p class="text-xs text-slate-500 mt-1 ml-1">+ ${b.count - 5} more…</p>` : ""}
        `}
      </div>`).join("");
  }

  // ---------------------------------------------- recent payments / inquiries
  function renderPayments(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const rows = settled.value.data || [];
    if (!rows.length) { el.innerHTML = UI.empty("No payments yet."); return; }
    el.innerHTML = `
      <table class="data-table w-full">
        <thead><tr><th>Case</th><th>Receipt</th><th class="text-right">Amount</th><th>Date</th></tr></thead>
        <tbody>${rows.map(p => `
          <tr>
            <td><a href="#/case/${encodeURIComponent(p.case_id)}" class="text-brand-600 hover:underline">${UI.escape(p.case_id)}</a></td>
            <td>${UI.escape(p.receipt_number || "—")}</td>
            <td class="text-right font-medium">${UI.money(p.amount)}</td>
            <td class="text-slate-500 text-xs">${UI.date(p.payment_date)}</td>
          </tr>`).join("")}
        </tbody></table>`;
  }

  function renderInquiries(el, settled) {
    if (settled.status !== "fulfilled") { el.innerHTML = UI.errorBox(settled.reason); return; }
    const rows = settled.value.data || [];
    if (!rows.length) { el.innerHTML = UI.empty("No inquiries yet."); return; }
    el.innerHTML = `
      <table class="data-table w-full">
        <thead><tr><th>Caller</th><th>Mobile</th><th>Case</th><th class="text-right">Quoted</th></tr></thead>
        <tbody>${rows.map(q => `
          <tr>
            <td class="font-medium">${UI.escape(q.caller_name)}</td>
            <td class="text-slate-500">${UI.escape(q.mobile_number || "—")}</td>
            <td><a href="#/case/${encodeURIComponent(q.case_id)}" class="text-brand-600 hover:underline">${UI.escape(q.case_id)}</a></td>
            <td class="text-right">${UI.money(q.amount_quoted)}</td>
          </tr>`).join("")}
        </tbody></table>`;
  }

  return { render };
})();
