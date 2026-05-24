/* ==================================================================
 * Raid Management System — Imports tab logic (PR2, additive).
 *
 * Reuses globals from app.js:  API, $, $$, toast, escapeHtml, fmtMoney
 *
 * Endpoints used (all backend additions in PR2):
 *   POST /api/rates/upload-schedule         (multipart)
 *   POST /api/historical/upload             (multipart)
 *   GET  /api/rates/schedules
 *   POST /api/rates/check-overlaps
 *
 * No existing app.js function is overridden. The script attaches its
 * own event listeners scoped to the new #panel-imports section.
 * ================================================================== */

(function () {
  "use strict";

  // ---- Multipart helper (API.req in app.js is JSON-only) ---------
  async function postMultipart(path, formData) {
    let env;
    try {
      const res = await fetch(API.base + path, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" },
      });
      const text = await res.text();
      try { env = JSON.parse(text); }
      catch { env = { ok: false, error: `Non-JSON ${res.status}: ${text.slice(0, 200)}` }; }
    } catch (e) {
      env = { ok: false, error: "Network: " + e.message };
    }
    return env;
  }

  // ---- Upload tariff schedule ------------------------------------
  async function uploadTariffSchedule() {
    const fileEl  = $("#imp_tariff_file");
    const nameEl  = $("#imp_tariff_name");
    const fromEl  = $("#imp_tariff_eff_from");
    const toEl    = $("#imp_tariff_eff_to");
    const resBox  = $("#impTariffResult");

    if (!fileEl || !fileEl.files || fileEl.files.length === 0) {
      toast("Pick a tariff Excel file first", "error");
      return;
    }
    const fd = new FormData();
    fd.append("file", fileEl.files[0]);
    if (nameEl.value.trim()) fd.append("schedule_name",  nameEl.value.trim());
    if (fromEl.value)        fd.append("effective_from", fromEl.value);
    if (toEl.value)          fd.append("effective_to",   toEl.value);
    fd.append("source", "imports_tab");

    resBox.textContent = "Uploading…";
    const env = await postMultipart("/api/rates/upload-schedule", fd);
    if (!env.ok) {
      resBox.innerHTML = `<span class="err-text">${escapeHtml(env.error || "upload failed")}</span>`;
      toast("Upload failed: " + env.error, "error");
      return;
    }
    const d = env.data;
    resBox.innerHTML = `
      <table class="data-table"><tbody>
        <tr><th>Schedule</th><td><code>${escapeHtml(d.schedule_name || "")}</code></td></tr>
        <tr><th>Inserted rows</th><td class="num">${Number(d.inserted ?? 0)}</td></tr>
        <tr><th>Skipped (blank)</th><td class="num">${Number(d.skipped_blank ?? 0)}</td></tr>
        <tr><th>Effective</th><td>${escapeHtml(d.effective_from || "—")} → ${escapeHtml(d.effective_to || "—")}</td></tr>
        <tr><th>Saved to</th><td><code>${escapeHtml(d.saved_to || "")}</code></td></tr>
        <tr><th>Time</th><td class="num">${Number(d.duration_ms ?? 0)} ms</td></tr>
      </tbody></table>`;
    toast(`Tariff schedule '${d.schedule_name}' inserted ${d.inserted} rows`, "ok");
    refreshSchedules();
  }

  // ---- Upload historical offenses --------------------------------
  async function uploadHistorical() {
    const fileEl   = $("#imp_hist_file");
    const sourceEl = $("#imp_hist_source");
    const resBox   = $("#impHistResult");

    if (!fileEl || !fileEl.files || fileEl.files.length === 0) {
      toast("Pick a historical Excel file first", "error");
      return;
    }
    const fd = new FormData();
    fd.append("file", fileEl.files[0]);
    if (sourceEl.value.trim()) fd.append("source", sourceEl.value.trim());

    resBox.textContent = "Uploading…";
    const env = await postMultipart("/api/historical/upload", fd);
    if (!env.ok) {
      resBox.innerHTML = `<span class="err-text">${escapeHtml(env.error || "upload failed")}</span>`;
      toast("Upload failed: " + env.error, "error");
      return;
    }
    const d = env.data;
    const headersMap = d.headers_mapped || {};
    const mappedRows = Object.entries(headersMap).map(
      ([raw, canon]) => `<tr><td><code>${escapeHtml(raw)}</code></td><td>→</td><td><code>${escapeHtml(canon)}</code></td></tr>`
    ).join("") || `<tr><td colspan="3" class="small center">No columns mapped (check headers).</td></tr>`;
    const errs = (d.errors || []).slice(0, 5).map(
      e => `<li>row ${e.row}: ${escapeHtml(e.error)}</li>`
    ).join("");
    resBox.innerHTML = `
      <table class="data-table"><tbody>
        <tr><th>File</th><td><code>${escapeHtml(d.file || "")}</code></td></tr>
        <tr><th>Total rows</th><td class="num">${Number(d.rows_total ?? 0)}</td></tr>
        <tr><th>Inserted</th><td class="num">${Number(d.inserted ?? 0)}</td></tr>
        <tr><th>Skipped (blank)</th><td class="num">${Number(d.skipped_blank ?? 0)}</td></tr>
        <tr><th>Skipped (duplicate)</th><td class="num">${Number(d.skipped_duplicate ?? 0)}</td></tr>
        <tr><th>Time</th><td class="num">${Number(d.duration_ms ?? 0)} ms</td></tr>
      </tbody></table>
      <details class="imp-details">
        <summary>Header mapping (${Object.keys(headersMap).length})</summary>
        <table class="data-table small">
          <tbody>${mappedRows}</tbody>
        </table>
      </details>
      ${errs ? `<div class="err-text"><b>Errors (first 5):</b><ul>${errs}</ul></div>` : ""}`;
    toast(`Historical: ${d.inserted} inserted, ${d.skipped_duplicate} dup`, "ok");
  }

  // ---- Refresh schedule list -------------------------------------
  async function refreshSchedules() {
    const tbody = $("#schedulesBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" class="small center">Loading…</td></tr>`;
    const env = await API.get("/api/rates/schedules");
    if (!env.ok) {
      tbody.innerHTML = `<tr><td colspan="6" class="err-text">${escapeHtml(env.error)}</td></tr>`;
      return;
    }
    const list = (env.data && env.data.schedules) || [];
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="small center">No tariff schedules uploaded yet.</td></tr>`;
      $("#overlapWarning").style.display = "none";
      return;
    }
    tbody.innerHTML = list.map(s => `
      <tr data-schedule="${escapeHtml(s.schedule_name)}">
        <td><code>${escapeHtml(s.schedule_name)}</code></td>
        <td>${(s.categories || []).map(c => `<span class="pill">${escapeHtml(c)}</span>`).join(" ")}</td>
        <td>${escapeHtml(s.earliest || "—")}</td>
        <td>${escapeHtml(s.latest   || "—")}</td>
        <td class="num">${Number(s.rows ?? 0)}</td>
        <td>
          <button class="btn small" data-check-schedule="${escapeHtml(s.schedule_name)}">Check overlaps</button>
        </td>
      </tr>`).join("");
  }

  // ---- Schedule overlap check (uses first category in schedule) --
  async function checkScheduleOverlaps(scheduleName) {
    const env = await API.get(`/api/rates/schedule/${encodeURIComponent(scheduleName)}`);
    if (!env.ok) {
      toast("Schedule fetch failed: " + env.error, "error");
      return;
    }
    const rows = (env.data && env.data.rows) || [];
    if (!rows.length) {
      toast(`'${scheduleName}' has no rows`, "error");
      return;
    }
    const conflicts = [];
    // Per row, ask backend to detect overlaps with OTHER schedules
    for (const r of rows) {
      const env2 = await API.post("/api/rates/check-overlaps", {
        category:        r.category,
        slab_start:      r.slab_start,
        slab_end:        r.slab_end,
        effective_from:  r.effective_from || r.schedule_effective_from,
        effective_to:    r.effective_to   || r.schedule_effective_to,
        condition_load:  r.condition_load,
        exclude_id:      r.id,
      });
      if (env2.ok) {
        const others = (env2.data.overlaps || []).filter(
          o => o.schedule_name !== scheduleName);
        for (const o of others) {
          conflicts.push({ source: r, other: o });
        }
      }
    }
    const box = $("#overlapWarning");
    if (!conflicts.length) {
      box.style.display = "block";
      box.innerHTML = `<b>✓ No overlaps</b> — '${escapeHtml(scheduleName)}' is disjoint from every other active schedule.`;
      box.className = "card overlap-warning ok";
      toast(`No overlaps for ${scheduleName}`, "ok");
      return;
    }
    box.style.display = "block";
    box.className = "card overlap-warning warn";
    const sample = conflicts.slice(0, 8).map(c => `
      <li>
        <code>${escapeHtml(c.source.category)}</code>
        slab ${escapeHtml(String(c.source.slab_start ?? 0))}–${escapeHtml(c.source.slab_end == null ? "∞" : String(c.source.slab_end))}
        (${escapeHtml(c.source.effective_from || c.source.schedule_effective_from || "—")}…${escapeHtml(c.source.effective_to || c.source.schedule_effective_to || "—")})
        ↔ schedule
        <code>${escapeHtml(c.other.schedule_name || "—")}</code>
      </li>`).join("");
    box.innerHTML = `
      <b>⚠ ${conflicts.length} overlap(s) detected</b> for
      <code>${escapeHtml(scheduleName)}</code>:
      <ul>${sample}</ul>
      ${conflicts.length > 8 ? `<p class="small">…and ${conflicts.length - 8} more.</p>` : ""}`;
    toast(`${conflicts.length} overlap(s) — see warning panel`, "error");
  }

  // ---- Wire up ---------------------------------------------------
  function init() {
    if (!$("#panel-imports")) return;  // guard if panel absent

    document.body.addEventListener("click", (e) => {
      const t = e.target;
      if (!t || !t.dataset) return;
      if (t.dataset.action === "upload-tariff")     uploadTariffSchedule();
      if (t.dataset.action === "upload-historical") uploadHistorical();
      if (t.dataset.action === "refresh-schedules") refreshSchedules();
      if (t.dataset.checkSchedule)                  checkScheduleOverlaps(t.dataset.checkSchedule);
    });

    // Auto-load schedule list when Imports tab is opened
    const tabsEl = $("#tabs");
    if (tabsEl) {
      tabsEl.addEventListener("click", (e) => {
        if (e.target && e.target.dataset && e.target.dataset.tab === "imports") {
          refreshSchedules();
        }
      });
    }
  }

  // Run after app.js has populated globals
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
