/* ==================================================================
 * Raid Management System — local browser UI (vanilla JS).
 *
 * No external dependencies. Talks to /api/* endpoints. Two main
 * surfaces:
 *
 *   - "New Case"  — capture inspection, calculate, save, generate docs.
 *   - "Cases"     — Raid Master grid with payment / notice / repeat-theft
 *                   indicators and one-click document preview/print.
 * ================================================================== */

const API = {
  base: window.location.origin,
  async req(method, path, body) {
    const opts = { method, headers: { "Accept": "application/json" } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json; charset=utf-8";
      opts.body = JSON.stringify(body);
    }
    let env;
    try {
      const res = await fetch(this.base + path, opts);
      const text = await res.text();
      try { env = JSON.parse(text); }
      catch { env = { ok: false, error: `Non-JSON ${res.status}: ${text.slice(0,120)}` }; }
    } catch (e) {
      env = { ok: false, error: "Network: " + e.message };
    }
    return env;
  },
  get(p)        { return this.req("GET", p); },
  post(p, body) { return this.req("POST", p, body || {}); },
};

const $  = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => Array.from(root.querySelectorAll(s));

const STATE = {
  currentCaseId: null,
  devices: [],
  documentKinds: [],
  noticeBundle: [],
};

// ============================================================ toast
let _toastTimer = null;
function toast(msg, kind = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show " + kind;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}

function fmtMoney(n) {
  if (n === null || n === undefined || n === "") return "—";
  const x = Number(n);
  if (!isFinite(x)) return n;
  return x.toLocaleString("en-IN", { maximumFractionDigits: 2,
                                     minimumFractionDigits: 2 });
}
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");
}
function statusPill(status) {
  const s = (status || "").toLowerCase();
  let cls = "";
  if (["paid","cleared","closed"].includes(s)) cls = "green";
  else if (["partial","ongoing","pending"].includes(s)) cls = "blue";
  else if (["overdue","unpaid"].includes(s)) cls = "red";
  else if (["noticed","approaching","provisional","section3","section5","dispatched","responded"].includes(s)) cls = "yellow";
  return `<span class="pill ${cls}">${escapeHtml(status || "—")}</span>`;
}
function paymentPill(payment) {
  if (!payment) return "—";
  const map = { paid: "green", partial: "blue", unpaid: "red", no_due: "" };
  const cls = map[payment.status] ?? "";
  const txt = payment.status === "paid"
            ? `Paid ✓`
            : payment.status === "no_due"
            ? `—`
            : `${payment.status.toUpperCase()} · ${payment.percent}%`;
  return `<span class="pill ${cls}" title="₹${fmtMoney(payment.total_paid)} of ₹${fmtMoney(payment.total_assessment)} (balance ₹${fmtMoney(payment.balance)})">${txt}</span>`;
}
function progressBar(percent, status) {
  const pc = Math.min(100, Math.max(0, Number(percent) || 0));
  const cls = status === "paid" ? "green"
            : status === "partial" ? "blue"
            : status === "unpaid" ? "red" : "";
  return `<div class="progress"><div class="progress-fill ${cls}" style="width:${pc}%"></div><span>${pc.toFixed(0)}%</span></div>`;
}

// ============================================================ tabs
function activateTab(name) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + name));
}
$("#tabs").addEventListener("click", (e) => {
  if (e.target.matches(".tab")) activateTab(e.target.dataset.tab);
});

// ============================================================ health
async function refreshHealth() {
  const dot = $("#healthDot"), txt = $("#healthText");
  dot.className = "dot busy";
  txt.textContent = "checking…";
  const env = await API.get("/api/health");
  if (env.ok && env.data && env.data.db_ok) {
    dot.className = "dot ok";
    txt.textContent = `OK · v${env.data.version} · py ${env.data.python}`;
  } else {
    dot.className = "dot fail";
    txt.textContent = "OFFLINE · " + (env.error || "unknown");
  }
}

async function loadDocumentKinds() {
  const env = await API.get("/api/document/kinds");
  if (env.ok) {
    STATE.documentKinds = env.data.kinds || [];
    STATE.noticeBundle  = env.data.notice_bundle || [];
  }
}

// ============================================================ DASHBOARD
async function refreshDashboard() {
  const env = await API.get("/api/dashboard/summary");
  if (env.ok) {
    const s = env.data;
    $("#kpiCases").textContent      = s.total_cases ?? 0;
    $("#kpiAssessment").textContent = fmtMoney(s.total_assessment ?? 0);
    $("#kpiPayCount").textContent   = s.today_payment_count ?? 0;
    $("#kpiPayAmt").textContent     = fmtMoney(s.today_payment_amount ?? 0);
  } else toast("Dashboard: " + env.error, "error");

  const a = await API.get("/api/dashboard/timeline-alerts");
  if (a.ok) {
    const alerts = a.data?.alerts || [];
    if (alerts.length === 0) {
      $("#alertsBox").textContent = "No pending timeline alerts.";
    } else {
      $("#alertsBox").innerHTML = alerts.map(it =>
        `<div>${statusPill(it.severity || it.kind)}
          <b>${escapeHtml(it.case_id || "")}</b>
          ${escapeHtml(it.message || it.kind || "")}</div>`
      ).join("");
    }
  }

  // Last backup info
  const b = await API.get("/api/backup/status");
  if (b.ok) {
    const s = b.data;
    if (s.latest) {
      $("#lastBackup").innerHTML =
        `Latest: <code>${escapeHtml(s.latest.name)}</code> (${s.latest.size_kb} KB) · ${escapeHtml(s.latest.modified)}`;
    } else {
      $("#lastBackup").textContent = "No backups yet.";
    }
  }
}

async function importMaster() {
  toast("Running import…");
  const env = await API.post("/api/import_all_master_data");
  if (!env.ok) { toast("Import failed: " + env.error, "error"); return; }
  const reports = env.data?.reports || {};
  const rows = Object.entries(reports).map(([kind, r]) => `
    <tr>
      <td>${escapeHtml(kind)}</td>
      <td class="num">${r.total_rows ?? 0}</td>
      <td class="num">${r.inserted ?? 0}</td>
      <td class="num">${r.updated ?? 0}</td>
      <td class="num">${r.skipped ?? 0}</td>
      <td class="num">${r.error_count ?? 0}</td>
      <td>${escapeHtml((r.warnings || []).join(" | "))}</td>
    </tr>`).join("");
  $("#importReportBox").innerHTML = `
    <table class="data-table"><thead><tr>
      <th>Kind</th><th>Total</th><th>Inserted</th><th>Updated</th>
      <th>Skipped</th><th>Errors</th><th>Warnings</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  toast("Import done", "ok");
}

// ============================================================ NEW CASE
function devicesAddRow(d) {
  const row = d || { name: "", load: "", factor: 1, hours: "", days: 365, units: "" };
  STATE.devices.push(row);
  renderDevices();
}

function renderDevices() {
  const body = $("#devicesBody");
  body.innerHTML = STATE.devices.map((d, i) => `
    <tr data-idx="${i}">
      <td>${i+1}</td>
      <td><input data-field="name"   value="${escapeHtml(d.name)}" /></td>
      <td><input data-field="load"   type="number" step="0.01" value="${escapeHtml(d.load)}" /></td>
      <td><input data-field="factor" type="number" step="0.01" value="${escapeHtml(d.factor)}" /></td>
      <td><input data-field="hours"  type="number" step="0.1"  value="${escapeHtml(d.hours)}" /></td>
      <td><input data-field="days"   type="number" step="1"    value="${escapeHtml(d.days)}" /></td>
      <td class="num">${d.units !== "" && d.units !== undefined ? Number(d.units).toFixed(2) : "—"}</td>
      <td><button class="btn small" data-remove="${i}">×</button></td>
    </tr>
  `).join("");
}

$("#devicesBody").addEventListener("input", (e) => {
  const tr = e.target.closest("tr"); if (!tr) return;
  const idx = Number(tr.dataset.idx);
  const fld = e.target.dataset.field;
  if (!fld) return;
  STATE.devices[idx][fld] = e.target.value;
});
$("#devicesBody").addEventListener("click", (e) => {
  if (e.target.dataset.remove !== undefined) {
    STATE.devices.splice(Number(e.target.dataset.remove), 1);
    renderDevices();
  }
});

function collectDevicesFromUI() {
  $$("#devicesBody tr").forEach(tr => {
    const idx = Number(tr.dataset.idx);
    $$("input", tr).forEach(inp => {
      STATE.devices[idx][inp.dataset.field] = inp.value;
    });
  });
  return STATE.devices
    .filter(d => d.name && (d.load || d.load === 0))
    .map(d => ({
      name:   d.name,
      load:   Number(d.load) || 0,
      factor: Number(d.factor) || 1,
      hours:  Number(d.hours) || 0,
      days:   Number(d.days)  || 0,
    }));
}

function buildCaseRequest() {
  return {
    account_number:    $("#f_account").value.trim(),
    name:              $("#f_name").value.trim(),
    father_name:       $("#f_father").value.trim(),
    village:           $("#f_village").value.trim(),
    post_office:       $("#f_post").value.trim(),
    pin_code:          $("#f_pin").value.trim(),
    mobile:            $("#f_mobile").value.trim(),
    section:           $("#f_section").value,
    inspection_date:   $("#f_inspection").value || null,
    category:          $("#f_category").value,
    connected_load_kw: Number($("#f_load").value) || 0,
    supply_type:       $("#f_supply").value,
    je_name:           $("#f_je").value.trim(),
    sub_substation:    $("#f_substation").value.trim(),
    checking_type:     $("#f_checking").value,
    devices:           collectDevicesFromUI(),
    calculate_compounding: true,
    created_by: "browser_ui",
  };
}

async function liveCalc() {
  const devices = collectDevicesFromUI();
  if (devices.length === 0) { toast("Add at least one device", "error"); return; }
  const env = await API.post("/api/calculate", {
    section: $("#f_section").value,
    category: $("#f_category").value,
    connected_load_kw: Number($("#f_load").value) || 0,
    inspection_date: $("#f_inspection").value || null,
    devices,
  });
  if (!env.ok) { toast("Calculate failed: " + env.error, "error"); return; }
  const d = env.data;
  d.devices.forEach((row, i) => { if (STATE.devices[i]) STATE.devices[i].units = row.units; });
  renderDevices();

  $("#calcResult").innerHTML = `
    <table class="data-table"><tbody>
      <tr><th>Total Units</th><td class="num">${fmtMoney(d.total_units_after_less_unit)}</td></tr>
      <tr><th>Months</th><td class="num">${fmtMoney(d.months)}</td></tr>
      <tr><th>Multiplier</th><td class="num">${d.multiplier}×</td></tr>
      <tr><th>Fixed Charges</th><td class="num">₹ ${fmtMoney(d.fixed_charges.final)}</td></tr>
      <tr><th>Energy Charges</th><td class="num">₹ ${fmtMoney(d.energy_charges.final)}</td></tr>
      <tr><th>ED (${d.electricity_duty.ed_percent}%)</th><td class="num">₹ ${fmtMoney(d.electricity_duty.amount)}</td></tr>
      <tr class="grand"><th>GRAND TOTAL</th><td class="num"><b>₹ ${fmtMoney(d.grand_total)}</b></td></tr>
    </tbody></table>
    ${(d.warnings||[]).length ? `<p style="color:var(--warn);font-size:12px">${d.warnings.map(escapeHtml).join("<br>")}</p>` : ""}
  `;
}

async function saveCase() {
  const req = buildCaseRequest();
  if (!req.account_number) { toast("Account No. is required", "error"); return; }
  if (req.devices.length === 0) { toast("Add at least one device", "error"); return; }
  const env = await API.post("/api/cases", req);
  if (!env.ok) { toast("Save failed: " + env.error, "error"); return; }
  const c = env.data.case;
  STATE.currentCaseId = c.case_id;
  $("#savedCase").innerHTML = `
    <div><b>Saved (${env.data.action}):</b> <code>${c.case_id}</code></div>
    <div>Account: <code>${escapeHtml(c.account_number)}</code></div>
    <div>Total Assessment: ₹ ${fmtMoney(c.total_assessment)}</div>
    <div>Compounding: ₹ ${fmtMoney(c.compounding_amount)}</div>
    <div>Status: ${statusPill(c.case_status)}</div>
  `;
  toast("Case saved: " + c.case_id, "ok");
}

async function offenseCheckActive() {
  const acct = $("#f_account").value.trim();
  if (!acct) { toast("Enter account first", "error"); return; }
  const env = await API.get(`/api/consumers/${encodeURIComponent(acct)}/offense-check`);
  if (!env.ok) { toast("Offense check failed: " + env.error, "error"); return; }
  const d = env.data, h = d.history;
  const msg = `Offenses: ${h.total_offenses} · Repeat: ${d.is_repeat_offender} · Suggested ${d.suggested_multiplier}×`;
  toast(msg, d.is_repeat_offender ? "error" : "ok");
}

async function generateAllForCurrent() {
  const cid = STATE.currentCaseId;
  if (!cid) { toast("Save the case first", "error"); return; }
  await generateAllForCase(cid);
}

async function generateAllForCase(cid) {
  toast(`Generating all notices for ${cid}…`);
  const env = await API.post(`/api/cases/${cid}/documents/generate-all`, {});
  if (!env.ok) { toast("Generate failed: " + env.error, "error"); return; }
  const d = env.data;
  toast(`Generated ${d.ok}/${d.total} documents · saved under docs/${cid}/`,
        d.failed ? "error" : "ok");
  // Also refresh the case detail if we're showing it
  if (STATE.currentCaseId === cid) await loadCase(cid);
}

// ============================================================ CASES — RAID MASTER
function repeatBadge(off) {
  if (!off || !off.is_repeat) return "";
  return `<span class="pill red" title="${escapeHtml(off.alert)}">⚠ REPEAT ${off.total_offenses}×</span>`;
}

function noticeBadge(n) {
  if (!n || !n.latest_type) return `<span class="small">none</span>`;
  let extra = "";
  if (n.overdue_section5) extra = ` <span class="pill red">SEC 5 OVERDUE</span>`;
  else if (n.overdue_section3) extra = ` <span class="pill red">SEC 3 OVERDUE</span>`;
  return `${statusPill(n.latest_type)} ${extra} <span class="small">×${n.count}</span>`;
}

async function refreshCases() {
  const env = await API.get("/api/cases/search?page_size=200");
  if (!env.ok) { toast("Cases: " + env.error, "error"); return; }
  const list = env.data || [];
  const filter = $("#cases_filter").value.trim().toLowerCase();
  const filtered = !filter ? list : list.filter(c =>
    [c.case_id, c.account_number, c.consumer_name, c.case_status,
     c.section, c.je_name, c.consumer_village]
      .some(v => (v || "").toString().toLowerCase().includes(filter)));

  const body = $("#casesBody");
  body.innerHTML = filtered.map(c => {
    const p = c.payment_summary || {};
    const n = c.notice_summary  || {};
    const o = c.offense_info    || {};
    const colorClass = c.row_color ? `row-${c.row_color}` : "";
    return `
      <tr class="${colorClass}">
        <td><code>${escapeHtml(c.case_id)}</code><br/>
            <span class="small">${escapeHtml(c.account_number || "")}</span></td>
        <td>${escapeHtml(c.consumer_name || "")}<br/>
            <span class="small">${escapeHtml(c.consumer_village || "")}</span>
            ${repeatBadge(o)}</td>
        <td>${escapeHtml(c.section || "")}<br/>
            <span class="small">${escapeHtml(c.inspection_date || "")}</span></td>
        <td class="num">${fmtMoney(c.total_assessment)}<br/>
            <span class="small">+ ${fmtMoney(c.compounding_amount || 0)}</span></td>
        <td>${paymentPill(p)}<br/>
            ${progressBar(p.percent, p.status)}</td>
        <td>${noticeBadge(n)}</td>
        <td>${statusPill(c.case_status)}</td>
        <td class="actions-col">
          <button class="btn small primary" data-load-case="${escapeHtml(c.case_id)}">Open</button>
          <button class="btn small" data-gen-all="${escapeHtml(c.case_id)}">Gen All</button>
        </td>
      </tr>`;
  }).join("") || `<tr><td colspan="8" style="text-align:center;color:var(--muted)">No cases yet.</td></tr>`;

  $("#casesCount").textContent = `${filtered.length} of ${list.length} cases`;

  // Color legend
  const counts = list.reduce((acc, c) => {
    acc[c.row_color || "none"] = (acc[c.row_color || "none"] || 0) + 1;
    return acc;
  }, {});
  $("#casesLegend").innerHTML = `
    <span class="legend-item"><span class="swatch green"></span> Paid (${counts.green || 0})</span>
    <span class="legend-item"><span class="swatch blue"></span>  Partial (${counts.blue || 0})</span>
    <span class="legend-item"><span class="swatch yellow"></span> Pending / Sec 3 due (${counts.yellow || 0})</span>
    <span class="legend-item"><span class="swatch red"></span>    Overdue / Sec 5 (${counts.red || 0})</span>`;
}

$("#cases_filter").addEventListener("input", () => refreshCases());
$("#casesBody").addEventListener("click", async (e) => {
  if (e.target.dataset.loadCase) await loadCase(e.target.dataset.loadCase);
  else if (e.target.dataset.genAll) await generateAllForCase(e.target.dataset.genAll);
});

async function loadCase(cid) {
  STATE.currentCaseId = cid;
  const env = await API.get(`/api/cases/${cid}`);
  if (!env.ok) { toast("Case: " + env.error, "error"); return; }
  const c = env.data.case;
  const consumer = env.data.consumer || {};

  $("#casesDetailHeader").style.display = "";
  $("#casesDetail").style.display = "";
  $("#casesDetail").innerHTML = `
    <div class="detail-grid">
      <div><b>${escapeHtml(c.case_id)}</b> · ${statusPill(c.case_status)}</div>
      <div>Account: <code>${escapeHtml(c.account_number || "")}</code></div>
      <div>Consumer: ${escapeHtml(consumer.name || "")} · ${escapeHtml(consumer.village || "")}</div>
      <div>Section: ${escapeHtml(c.section || "")} · Inspection: ${escapeHtml(c.inspection_date || "")}</div>
      <div>Assessment: ₹ <b>${fmtMoney(c.total_assessment)}</b></div>
      <div>Compounding: ₹ ${fmtMoney(c.compounding_amount)}</div>
      <div>J.E.: ${escapeHtml(c.je_name || "")}</div>
      <div>Sub-station: ${escapeHtml(c.sub_substation || "")}</div>
    </div>`;

  // Document toolbar — Generate All + per-doc Preview/Print
  $("#docToolbarHeader").style.display = "";
  $("#docToolbarWrap").style.display = "";
  const buttons = (STATE.noticeBundle.length ? STATE.noticeBundle : STATE.documentKinds)
    .map(kind => `
      <a class="btn small" target="_blank" rel="noopener"
         href="/api/cases/${encodeURIComponent(cid)}/document/${kind}/preview">
        ${kind.replace(/_/g, " ")}
      </a>`).join("");
  $("#docToolbar").innerHTML = `
    <button class="btn primary" data-action="gen-all-current">📄 Generate All Notices</button>
    <span class="vbar"></span>
    <span class="small">Preview &amp; Print:</span>
    ${buttons}
  `;

  $("#casesPaymentsHeader").style.display = "";
  $("#casesPaymentsWrap").style.display = "";
  await refreshPayments();

  $("#casesNoticesHeader").style.display = "";
  $("#casesNoticesWrap").style.display = "";
  await refreshNotices();

  // Existing generated docs list
  $("#caseDocsHeader").style.display = "";
  $("#caseDocsWrap").style.display = "";
  const docs = env.data.documents || [];
  $("#caseDocsBody").innerHTML = docs.map(d => `
    <tr>
      <td>${escapeHtml(d.document_type)}</td>
      <td><code>${escapeHtml(d.document_name)}</code></td>
      <td class="num">${(d.file_size / 1024).toFixed(1)} KB</td>
      <td>${escapeHtml(d.created_at)}</td>
      <td>
        <a class="btn small" target="_blank" href="/api/cases/${encodeURIComponent(cid)}/document/${d.document_type}/preview">🖨 Print</a>
        <a class="btn small" href="/api/documents/${d.id}">⬇ DOCX</a>
      </td>
    </tr>`).join("") || `<tr><td colspan="5" class="small center">No documents generated yet.</td></tr>`;

  toast("Loaded " + cid);
}

async function refreshPayments() {
  if (!STATE.currentCaseId) return;
  const env = await API.get(`/api/cases/${STATE.currentCaseId}/payments`);
  if (!env.ok) { toast("Payments: " + env.error, "error"); return; }
  const list = env.data?.payments || [];
  $("#paymentsBody").innerHTML = list.map(p => `
    <tr>
      <td>${escapeHtml(p.payment_date || "")}</td>
      <td class="num">${fmtMoney(p.amount)}</td>
      <td>${escapeHtml(p.payment_type || "")}</td>
      <td>${escapeHtml(p.component || "")}</td>
      <td>${escapeHtml(p.receipt_number || "")}</td>
      <td>${escapeHtml(p.payment_method || "")}</td>
      <td>${escapeHtml(p.remarks || "")}</td>
    </tr>`).join("") || `<tr><td colspan="7" style="text-align:center;color:var(--muted)">No payments yet.</td></tr>`;
}

async function recordPayment() {
  if (!STATE.currentCaseId) { toast("Open a case first", "error"); return; }
  const amount = Number(prompt("Amount?", "5000"));
  if (!amount || isNaN(amount)) return;
  const receipt = prompt("Receipt number?", "RC-001") || "";
  const method  = prompt("Method (cash/online/cheque)?", "cash") || "cash";
  const comp    = prompt("Component (assessment/compounding/admin)?", "assessment") || "assessment";
  const env = await API.post(`/api/cases/${STATE.currentCaseId}/payments`, {
    amount, payment_type: "partial", component: comp,
    receipt_number: receipt, payment_method: method, user: "browser_ui",
  });
  if (!env.ok) { toast("Pay failed: " + env.error, "error"); return; }
  toast("Payment recorded · balance ₹ " + fmtMoney(env.data?.summary?.balance), "ok");
  refreshPayments();
}

async function refreshNotices() {
  if (!STATE.currentCaseId) return;
  const env = await API.get(`/api/cases/${STATE.currentCaseId}/notices`);
  if (!env.ok) return;
  const list = env.data || [];
  $("#noticesBody").innerHTML = list.map(n => `
    <tr>
      <td>${escapeHtml(n.notice_type || "")}</td>
      <td>${escapeHtml(n.notice_number || "")}</td>
      <td>${escapeHtml(n.dispatch_date || n.notice_date || "")}</td>
      <td>${escapeHtml(n.due_date || "")}</td>
      <td>${statusPill(n.status)}</td>
    </tr>`).join("") || `<tr><td colspan="5" style="text-align:center;color:var(--muted)">No notices yet.</td></tr>`;
}

async function addNotice(kind) {
  if (!STATE.currentCaseId) { toast("Open a case first", "error"); return; }
  const num = prompt(`${kind} notice number?`,
                     `${kind.toUpperCase().slice(0,2)}-${Date.now()}`);
  if (!num) return;
  const env = await API.post(`/api/cases/${STATE.currentCaseId}/notices`, {
    notice_type: kind, notice_number: num, user: "browser_ui",
  });
  if (!env.ok) { toast("Notice failed: " + env.error, "error"); return; }
  toast(`Notice added · due ${env.data?.due_date}`, "ok");
  refreshNotices();
}

// ============================================================ SEARCH
async function runSearch() {
  const q = new URLSearchParams();
  if ($("#s_account").value.trim()) q.set("account", $("#s_account").value.trim());
  if ($("#s_name").value.trim())    q.set("name",    $("#s_name").value.trim());
  if ($("#s_village").value.trim()) q.set("village", $("#s_village").value.trim());
  if ([...q.keys()].length === 0) { toast("Enter at least one field", "error"); return; }
  const env = await API.get("/api/consumers/search?" + q);
  if (!env.ok) { toast("Search: " + env.error, "error"); return; }
  const list = env.data || [];
  $("#searchBody").innerHTML = list.map(r => `
    <tr>
      <td><code>${escapeHtml(r.account_number || "")}</code></td>
      <td>${escapeHtml(r.name || "")}</td>
      <td>${escapeHtml(r.father_name || "")}</td>
      <td>${escapeHtml(r.village || "")}</td>
      <td>${escapeHtml(r.mobile || "")}</td>
      <td>${escapeHtml(r.category || "")}</td>
      <td><button class="btn small" data-fill-acct="${escapeHtml(r.account_number || "")}">Use</button></td>
    </tr>`).join("") || `<tr><td colspan="7" style="text-align:center;color:var(--muted)">No results.</td></tr>`;
  toast(`${list.length} result(s)`, list.length ? "ok" : "");
}
$("#searchBody").addEventListener("click", (e) => {
  const acct = e.target.dataset.fillAcct;
  if (!acct) return;
  $("#f_account").value = acct;
  activateTab("new-case");
  toast("Account copied to New Case → " + acct, "ok");
});

// ============================================================ BACKUP
async function backupNow() {
  toast("Creating backup…");
  const env = await API.post("/api/backup/now", {});
  if (!env.ok) { toast("Backup failed: " + env.error, "error"); return; }
  const d = env.data;
  const gd = d.gdrive || {};
  toast(`Backup OK · ${d.zip_name} (${(d.zip_size/1024).toFixed(1)} KB)` +
        (gd.ok ? ` · Drive uploaded` : ` · Drive ${gd.skipped ? "skipped" : "failed"}`),
        "ok");
  refreshBackups();
  refreshDashboard();
}
async function refreshBackups() {
  const env = await API.get("/api/backup/list");
  if (!env.ok) return;
  const list = env.data || [];
  $("#backupBody").innerHTML = list.map(b => `
    <tr>
      <td><code>${escapeHtml(b.name)}</code></td>
      <td class="num">${b.size_kb}</td>
      <td>${escapeHtml(b.modified)}</td>
      <td><a class="btn small" href="/api/backup/download/${encodeURIComponent(b.name)}">Download</a></td>
    </tr>`).join("") || `<tr><td colspan="4" style="text-align:center;color:var(--muted)">No backups yet.</td></tr>`;
}
async function backupStatus() {
  const env = await API.get("/api/backup/status");
  if (!env.ok) { $("#backupStatus").textContent = env.error; return; }
  const s = env.data;
  $("#backupStatus").innerHTML = `
    <div>Backup folder: <code>${escapeHtml(s.backup_dir)}</code></div>
    <div>DB size: ${(s.db_size/1024).toFixed(1)} KB · Backup count: ${s.backup_count}</div>
    <div>Google Drive: ${s.gdrive_enabled ? statusPill("paid") : statusPill("pending")}
         <span style="color:var(--muted)">${escapeHtml(s.gdrive_reason || "")}</span></div>
    ${s.latest ? `<div>Latest: <code>${escapeHtml(s.latest.name)}</code> (${s.latest.size_kb} KB) · ${escapeHtml(s.latest.modified)}</div>` : ""}
  `;
}

// ============================================================ REPORTS
async function generateReport(kind) {
  const path = kind === "dashboard" ? "/api/reports/dashboard.pdf"
                                    : `/api/reports/${kind}.xlsx`;
  toast("Generating " + kind + "…");
  const env = await API.get(path);
  if (!env.ok) { toast("Report failed: " + env.error, "error"); return; }
  toast(`${kind} ready · ${env.data.file}`, "ok");
  refreshReports();
}
async function refreshReports() {
  const env = await API.get("/api/reports/list");
  if (!env.ok) return;
  const list = env.data || [];
  $("#reportsBody").innerHTML = list.map(r => `
    <tr>
      <td><code>${escapeHtml(r.name)}</code></td>
      <td class="num">${r.size_kb}</td>
      <td>${escapeHtml(r.modified)}</td>
      <td><a class="btn small" href="/api/reports/download/${encodeURIComponent(r.name)}">Download</a></td>
    </tr>`).join("") || `<tr><td colspan="4" style="text-align:center;color:var(--muted)">No reports yet.</td></tr>`;
}

// ============================================================ central click router
document.addEventListener("click", (e) => {
  const action = e.target.dataset.action;
  if (!action) return;
  switch (action) {
    case "refresh-dashboard": refreshDashboard(); break;
    case "import-master":     importMaster(); break;
    case "backup-now":        backupNow(); break;
    case "refresh-backups":   refreshBackups(); break;
    case "backup-status":     backupStatus(); break;

    case "add-device":        devicesAddRow(); break;
    case "add-sample":
      STATE.devices = [
        { name: "Bulb / LED",   load: 9,    factor: 1, hours: 6,  days: 365, units: "" },
        { name: "Ceiling Fan",  load: 75,   factor: 1, hours: 12, days: 365, units: "" },
        { name: "AC 1.5 Ton",   load: 1800, factor: 1, hours: 4,  days: 120, units: "" },
      ];
      renderDevices();
      break;
    case "live-calc":         liveCalc(); break;
    case "save-case":         saveCase(); break;
    case "offense-check":     offenseCheckActive(); break;
    case "generate-all-docs": generateAllForCurrent(); break;
    case "gen-all-current":   generateAllForCurrent(); break;

    case "refresh-cases":     refreshCases(); break;
    case "record-payment":    recordPayment(); break;
    case "add-notice":        addNotice(e.target.dataset.kind); break;

    case "run-search":        runSearch(); break;

    case "report":            generateReport(e.target.dataset.kind); break;
    case "refresh-reports":   refreshReports(); break;
  }
});

// ============================================================ boot
window.addEventListener("DOMContentLoaded", async () => {
  $("#apiBase").textContent = API.base;
  await loadDocumentKinds();
  refreshHealth();
  refreshDashboard();
  refreshCases();
  $("#f_inspection").value = new Date().toISOString().slice(0, 10);
  setInterval(refreshHealth, 30000);
});
