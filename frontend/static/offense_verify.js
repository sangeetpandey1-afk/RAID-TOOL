/* ==================================================================
 * Raid Management System — Offense Auto Verification (PR4).
 *
 * Behaviour
 * ---------
 *  * Listens to #f_account (input + blur). Debounced 350 ms.
 *  * On change, GET /api/offense/lookup?account=… (account-number-only,
 *    indexed lookup against historical_cases — never fuzzy).
 *  * Renders one of three states inside #offenseVerify:
 *
 *      empty      — operator hasn't typed an account yet
 *      no_hits    — account is set but historical_cases has no rows
 *      hits       — at least one prior offense found
 *
 *    The card is collapsed by default in the "hits" state and shows
 *    a "expand" / "collapse" toggle with an offense-count badge.
 *    Expanding renders the full 15-column historical row table.
 *
 *  * Surfaces a Suggested Multiplier (2× / 6×) with an Apply button
 *    that ticks the existing #chk_multiplier override checkbox and
 *    fills #f_multiplier — leaving the operator free to change it.
 *
 * Reuses
 * ------
 *  API, $, $$, escapeHtml, fmtMoney, toast — from app.js
 * ================================================================== */

(function () {
  "use strict";

  const DEBOUNCE_MS = 350;
  const TARGET_FIELDS = [
    // The 15 PR4 display columns, in roadmap order.
    { key: "notice_no",        label: "Notice No." },
    { key: "div_no",           label: "Div. No." },
    { key: "case_date",        label: "Date" },
    { key: "name",             label: "Name" },
    { key: "father_name",      label: "Father Name" },
    { key: "use_name",         label: "Use Name" },
    { key: "user_father_name", label: "User Father Name" },
    { key: "address",          label: "Address" },
    { key: "sub_substation",   label: "Sub Station" },
    { key: "assessment_amount",label: "Assessment", money: true },
    { key: "old_account_id",   label: "Old AC No." },
    { key: "new_account_id",   label: "New Account Number" },
    { key: "category",         label: "Category" },
    { key: "irregularity",     label: "Irregularity" },
    { key: "paid_status",      label: "Paid/Unpaid" },
  ];

  let _timer = null;
  let _lastAccount = null;
  let _lastResult  = null;

  function setState(state, status) {
    const card = $("#offenseVerify");
    if (!card) return;
    card.dataset.state = state;
    const s = $("#ovStatus");
    if (s && status !== undefined) s.textContent = status;
  }

  function clearBody() {
    const body = $("#ovBody");
    if (body) {
      body.innerHTML = "";
      body.hidden = true;
    }
    const tog = $("#ovToggle");
    if (tog) {
      tog.style.display = "none";
      tog.setAttribute("aria-expanded", "false");
      tog.textContent = "expand";
    }
  }

  function showToggle(text) {
    const tog = $("#ovToggle");
    if (!tog) return;
    tog.style.display = "";
    tog.textContent = text;
  }

  // ---- Render: hits state -----------------------------------------
  function _formatCell(field, val) {
    if (val == null || val === "") return "<span class='ov-empty'>—</span>";
    if (field.money) return "₹ " + fmtMoney(val);
    if (field.key === "paid_status") {
      const v = String(val).toLowerCase();
      const cls = v === "paid"   ? "green"
                : v === "unpaid" ? "red"
                : "";
      return `<span class="pill ${cls}">${escapeHtml(val)}</span>`;
    }
    return escapeHtml(val);
  }

  function renderRows(rows) {
    if (!rows || !rows.length) return "";
    const headers = TARGET_FIELDS.map(
      f => `<th>${escapeHtml(f.label)}</th>`).join("");
    const trs = rows.map(r => {
      const tds = TARGET_FIELDS.map(
        f => `<td>${_formatCell(f, r[f.key])}</td>`).join("");
      return `<tr>${tds}</tr>`;
    }).join("");
    return `
      <div class="scroll-x">
        <table class="data-table ov-table">
          <thead><tr>${headers}</tr></thead>
          <tbody>${trs}</tbody>
        </table>
      </div>`;
  }

  function renderHits(d) {
    const sug = d.suggested_multiplier || 2;
    const isRepeat = !!d.is_repeat;
    const mult_class = sug >= 5 ? "red" : sug >= 3 ? "yellow" : "green";
    const status = `<b>${d.matched_count} prior offense${d.matched_count === 1 ? "" : "s"}</b>`
                 + ` on <code>${escapeHtml(d.account)}</code>`;
    setState("hits", "");
    $("#ovStatus").innerHTML = status;
    showToggle("expand");

    const dates =
      `${escapeHtml(d.first_offense_date || "—")} → ${escapeHtml(d.last_offense_date || "—")}`;

    const summaryHtml = `
      <div class="ov-summary">
        <div>
          <span class="ov-tag ${isRepeat ? "red" : "blue"}">
            ${isRepeat ? "⚠ REPEAT OFFENDER" : "first prior on file"}
          </span>
          <span class="small ov-dates">Range: ${dates}</span>
          <span class="small ov-total">Total prior assessment: ₹ ${fmtMoney(d.total_assessment || 0)}</span>
        </div>
        <div class="ov-multiplier">
          <span class="ov-mlabel">Suggested multiplier:</span>
          <span class="ov-mvalue ${mult_class}">${Number(sug).toFixed(1)}×</span>
          <button type="button" class="btn small primary" id="ovApplyMult">
            Apply
          </button>
        </div>
      </div>
      <div class="ov-rows" id="ovRows" hidden>
        ${renderRows(d.rows)}
      </div>`;

    const body = $("#ovBody");
    body.innerHTML = summaryHtml;
    body.hidden = false;
  }

  function renderNoHits(account) {
    setState("no_hits", "");
    const body = $("#ovBody");
    if (body) {
      body.innerHTML = `
        <div class="ov-empty-state">
          <span class="ov-tag green">✓ NO PRIOR OFFENSES</span>
          on <code>${escapeHtml(account)}</code>
          <span class="small">— suggested multiplier 2×</span>
        </div>`;
      body.hidden = false;
    }
    showToggle("hide");
  }

  function renderEmpty() {
    setState("empty",
      "type an account number above to auto-check prior offenses");
    clearBody();
  }

  // ---- Apply suggested multiplier --------------------------------
  function applySuggestedMultiplier() {
    if (!_lastResult) return;
    const sug = _lastResult.suggested_multiplier;
    if (!sug) return;
    const m  = $("#f_multiplier");
    const ck = $("#chk_multiplier");
    if (ck && !ck.checked) ck.checked = true;
    if (m) {
      m.value = sug;
      // Trigger any existing change listener so the gating logic fires
      m.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (typeof toast === "function") {
      toast(`Multiplier set to ${Number(sug).toFixed(1)}×`, "ok");
    }
  }

  // ---- Lookup -----------------------------------------------------
  async function runLookup(account) {
    if (!account) { renderEmpty(); return; }
    setState(_lastResult ? _lastResult._state : "loading",
      `looking up ${account}…`);
    const env = await API.get(
      "/api/offense/lookup?account=" + encodeURIComponent(account));
    if (!env.ok) {
      setState("error", `Lookup failed: ${env.error || "unknown"}`);
      clearBody();
      return;
    }
    const d = env.data || {};
    _lastResult = { ...d, _state: d.matched_count > 0 ? "hits" : "no_hits" };
    if (d.matched_count > 0) {
      renderHits(d);
    } else {
      renderNoHits(d.account || account);
    }
  }

  function debouncedLookup() {
    const v = ($("#f_account")?.value || "").trim();
    if (v === _lastAccount) return;
    _lastAccount = v;
    clearTimeout(_timer);
    if (!v) { renderEmpty(); return; }
    _timer = setTimeout(() => runLookup(v), DEBOUNCE_MS);
  }

  // ---- Wire-up ----------------------------------------------------
  function init() {
    if (!$("#offenseVerify") || !$("#f_account")) return;

    const acc = $("#f_account");
    acc.addEventListener("input", debouncedLookup);
    acc.addEventListener("blur", () => {
      // Run immediately on blur — bypass the debounce
      clearTimeout(_timer);
      const v = (acc.value || "").trim();
      if (v && v !== _lastAccount) { _lastAccount = v; runLookup(v); }
      else if (!v) { renderEmpty(); }
    });

    // Toggle expand/collapse
    document.body.addEventListener("click", (e) => {
      const t = e.target;
      if (!t) return;
      if (t.id === "ovToggle") {
        const rows = $("#ovRows");
        const tog  = $("#ovToggle");
        if (rows) {
          rows.hidden = !rows.hidden;
          tog.setAttribute("aria-expanded", String(!rows.hidden));
          tog.textContent = rows.hidden ? "expand" : "collapse";
        } else if ($("#ovBody")) {
          // No-hits state: toggle the small body
          $("#ovBody").hidden = !$("#ovBody").hidden;
          tog.textContent = $("#ovBody").hidden ? "show" : "hide";
        }
      }
      if (t.id === "ovApplyMult") {
        applySuggestedMultiplier();
      }
    });

    // Initial state — empty
    renderEmpty();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
