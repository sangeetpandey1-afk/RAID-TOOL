/* ==================================================================
 * Raid Management System — Imports panel DOM glue.
 * ------------------------------------------------------------------
 * Wires the new "Imports" top tab introduced by PR
 * feat/rate-master-tariff-timeline.  The panel hosts two cards:
 *
 *   A) Historical Offense Import   -> POST /api/historical/import
 *   B) Rate Master Import          -> POST /api/rates/import
 *      + a live grid of existing schedules     GET /api/rates/schedules
 *      + sample-workbook download              GET /api/rates/sample.xlsx
 *
 * Safety contract
 * ---------------
 * - Pure additive: does NOT modify app.js, mobile.js, the LFHD
 *   grouper, the Total Connected Load logic, or any save/load flow.
 *   Lives entirely on the new #panel-imports section.
 * - All AJAX uses the standard envelope shape ({ok, data, error,
 *   code}) and surfaces errors via toast() if available — falls back
 *   to alert() if the existing toast is unreachable.
 * - Idempotent: setup() can be invoked multiple times.  We guard via
 *   data-imports-ready on the panel root.
 *
 * Conflict resolution flow (rate import)
 * --------------------------------------
 * 1. Operator fills schedule_name + dates and picks a file.
 * 2. We submit with conflict_strategy=warn.
 * 3. If summary.overlaps is non-empty:
 *      - schedule was inserted (warn mode keeps it)
 *      - the panel surfaces a yellow notice listing overlapping
 *        schedules and offers "Replace existing" / "Cancel & rollback"
 *        / "Keep both (do nothing)" buttons.
 *      - "Replace existing" reuses the same payload but with
 *        conflict_strategy=replace and removes the just-imported
 *        schedule first (POST /activate {is_active:false}).
 * ================================================================== */

(function () {
  'use strict';

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;',
                '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  /** Best-effort toast — uses the existing app.js toast if present,
   *  falls back to a tiny inline notice element on the imports panel. */
  function notify(msg, kind) {
    if (typeof window.toast === 'function') {
      window.toast(msg, kind || 'ok');
      return;
    }
    var box = $('#importsToast');
    if (!box) return;
    box.textContent = msg;
    box.className = 'imports-toast ' + (kind === 'error' ? 'err' : 'ok');
    box.style.display = 'block';
    clearTimeout(notify._t);
    notify._t = setTimeout(function () { box.style.display = 'none'; }, 4500);
  }

  function fmtNum(n)  { return (n == null ? '—' : Number(n).toLocaleString()); }
  function fmtDate(s) { return s ? String(s) : '—'; }

  /** ------------------------------------------------------------- *
   *  CARD A — Historical Offense Import.                           *
   *  Existing endpoint /api/historical/import (PR #14).            *
   * ------------------------------------------------------------- */

  function setupHistoricalCard() {
    var form = $('#histImportForm');
    var input = $('#histImportFile');
    var summary = $('#histImportSummary');
    if (!form || !input || !summary) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!input.files || !input.files[0]) {
        notify('Pick a workbook first', 'error');
        return;
      }
      var fd = new FormData();
      fd.append('file', input.files[0]);
      summary.innerHTML = '<div class="small">Uploading…</div>';

      fetch('/api/historical/import', { method: 'POST', body: fd })
        .then(function (r) { return r.json(); })
        .then(function (env) {
          if (!env.ok) {
            summary.innerHTML = '<div class="imports-err">' +
              escapeHtml(env.error || 'Upload failed') + '</div>';
            notify(env.error || 'Upload failed', 'error');
            return;
          }
          var s = env.data.summary;
          summary.innerHTML = renderHistorySummary(s);
          notify('Historical import: ' + s.imported + ' new rows, ' +
                 s.duplicates + ' duplicates', 'ok');
          input.value = '';
        })
        .catch(function (err) {
          summary.innerHTML = '<div class="imports-err">' +
            escapeHtml(err.message || String(err)) + '</div>';
          notify('Upload error: ' + err.message, 'error');
        });
    });
  }

  function renderHistorySummary(s) {
    var errs = (s.errors || []).slice(0, 5).map(function (e) {
      return '<li>row ' + escapeHtml(e.row) + ': ' +
             escapeHtml(e.reason) + '</li>';
    }).join('');
    return (
      '<div class="imports-summary">' +
        '<div class="kpi-grid imports-kpis">' +
          '<div class="kpi"><div class="kpi-label">Total rows</div>' +
            '<div class="kpi-value">' + fmtNum(s.total_rows) + '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Imported</div>' +
            '<div class="kpi-value good">' + fmtNum(s.imported) + '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Duplicates</div>' +
            '<div class="kpi-value warn">' + fmtNum(s.duplicates) + '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Skipped</div>' +
            '<div class="kpi-value">' + fmtNum(s.skipped) + '</div></div>' +
        '</div>' +
        '<div class="small">' +
          'File: <code>' + escapeHtml(s.source_file || '') + '</code>' +
          (s.duration_ms != null ? '  ·  ' + s.duration_ms + ' ms' : '') +
        '</div>' +
        (errs ? '<details class="imports-errs"><summary>' +
                  s.errors.length + ' errors</summary><ul>' + errs +
                  (s.errors.length > 5
                    ? '<li class="small">…' + (s.errors.length - 5) + ' more</li>'
                    : '') +
                '</ul></details>' : '') +
      '</div>'
    );
  }

  /** ------------------------------------------------------------- *
   *  CARD B — Rate Master Import.                                  *
   *  Endpoint /api/rates/import (this PR).  Includes overlap       *
   *  detection + resolution UI.                                    *
   * ------------------------------------------------------------- */

  function setupRateCard() {
    var form = $('#rateImportForm');
    var input = $('#rateImportFile');
    var nameInput = $('#rateImportName');
    var fromInput = $('#rateImportFrom');
    var toInput   = $('#rateImportTo');
    var notesInput = $('#rateImportNotes');
    var summary = $('#rateImportSummary');
    var grid = $('#rateScheduleGrid');
    var sampleBtn = $('#rateSampleBtn');
    if (!form || !grid) return;

    function postImport(strategy, justImportedScheduleId) {
      if (!input.files || !input.files[0]) {
        notify('Pick a tariff workbook first', 'error');
        return Promise.resolve(null);
      }
      var fd = new FormData();
      fd.append('file',           input.files[0]);
      fd.append('schedule_name',  (nameInput.value  || '').trim());
      fd.append('effective_from', (fromInput.value  || '').trim());
      fd.append('effective_to',   (toInput.value    || '').trim());
      fd.append('notes',          (notesInput.value || '').trim());
      fd.append('conflict_strategy', strategy || 'warn');
      summary.innerHTML = '<div class="small">Uploading…</div>';

      // If we're "Replace"-ing after a warn-mode import landed, we
      // need to first deactivate the schedule we just inserted, so
      // detect_overlap inside the next /import call sees only the
      // *original* overlapping schedules.
      var pre = Promise.resolve();
      if (strategy === 'replace' && justImportedScheduleId) {
        pre = fetch('/api/rates/schedules/' + justImportedScheduleId +
                    '/activate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_active: false }),
        });
      }

      return pre.then(function () {
        return fetch('/api/rates/import', { method: 'POST', body: fd })
          .then(function (r) { return r.json(); });
      }).then(function (env) {
        if (!env.ok) {
          summary.innerHTML = '<div class="imports-err">' +
            escapeHtml(env.error || 'Upload failed') + '</div>';
          notify(env.error || 'Upload failed', 'error');
          return null;
        }
        renderRateSummary(env.data.summary, env.data.applied_strategy);
        loadSchedules();
        return env.data.summary;
      }).catch(function (err) {
        summary.innerHTML = '<div class="imports-err">' +
          escapeHtml(err.message || String(err)) + '</div>';
        notify('Upload error: ' + err.message, 'error');
        return null;
      });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!nameInput.value.trim()) {
        notify('Schedule name required', 'error');
        return;
      }
      postImport('warn', null);
    });

    summary.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-resolve]');
      if (!btn) return;
      var action = btn.dataset.resolve;
      var sid = parseInt(btn.dataset.scheduleId || '0', 10) || null;
      if (action === 'replace') {
        postImport('replace', sid).then(function (s) {
          if (s) notify('Replaced overlapping schedule(s)', 'ok');
        });
      } else if (action === 'cancel') {
        // Just deactivate the schedule we just created.
        if (!sid) return;
        fetch('/api/rates/schedules/' + sid + '/activate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_active: false }),
        }).then(function () {
          summary.innerHTML = '<div class="small">Schedule deactivated.</div>';
          notify('Schedule cancelled — deactivated', 'ok');
          loadSchedules();
        });
      } else if (action === 'keep') {
        var node = summary.querySelector('.imports-conflict');
        if (node) node.parentNode.removeChild(node);
        notify('Keeping both schedules — operator will reconcile manually', 'ok');
      }
    });

    sampleBtn && sampleBtn.addEventListener('click', function () {
      window.open('/api/rates/sample.xlsx', '_blank');
    });

    loadSchedules();

    function loadSchedules() {
      grid.innerHTML = '<div class="small">Loading…</div>';
      fetch('/api/rates/schedules')
        .then(function (r) { return r.json(); })
        .then(function (env) {
          if (!env.ok) {
            grid.innerHTML = '<div class="imports-err">' +
              escapeHtml(env.error || 'Failed to load schedules') + '</div>';
            return;
          }
          grid.innerHTML = renderScheduleGrid(env.data.schedules || []);
        });
    }

    grid.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-toggle-schedule]');
      if (!btn) return;
      var id = parseInt(btn.dataset.toggleSchedule, 10);
      var next = btn.dataset.next === '1';
      fetch('/api/rates/schedules/' + id + '/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: next }),
      })
        .then(function (r) { return r.json(); })
        .then(function (env) {
          if (env.ok) {
            notify('Schedule ' + (next ? 'activated' : 'deactivated'), 'ok');
            loadSchedules();
          } else {
            notify(env.error || 'Toggle failed', 'error');
          }
        });
    });
  }

  function renderRateSummary(s, strategy) {
    var conflict = '';
    if (s.overlaps && s.overlaps.length) {
      var rows = s.overlaps.map(function (o) {
        return '<li><b>' + escapeHtml(o.schedule_name) + '</b> ' +
               '<span class="small">(' + fmtDate(o.effective_from) +
               ' → ' + fmtDate(o.effective_to) + ')</span></li>';
      }).join('');
      var inserted = (s.schedule_id != null);
      var actions = inserted
        ? '<button class="btn primary small" data-resolve="replace" '   +
              'data-schedule-id="' + s.schedule_id + '">Replace existing</button>' +
          '<button class="btn small"        data-resolve="keep" '       +
              'data-schedule-id="' + s.schedule_id + '">Keep both</button>' +
          '<button class="btn small danger" data-resolve="cancel" '     +
              'data-schedule-id="' + s.schedule_id + '">Cancel &amp; rollback</button>'
        : '<div class="small">' +
              'Cancelled — no schedule was created (strategy=cancel).' +
          '</div>';
      conflict =
        '<div class="imports-conflict">' +
          '<div class="imports-conflict-title">' +
            '⚠ Effective-date conflict detected' +
          '</div>' +
          '<ul>' + rows + '</ul>' +
          '<div class="imports-conflict-actions">' + actions + '</div>' +
        '</div>';
    }

    var errs = (s.errors || []).slice(0, 5).map(function (e) {
      return '<li>row ' + escapeHtml(e.row) + ': ' +
             escapeHtml(e.reason) + '</li>';
    }).join('');

    summary.innerHTML =
      '<div class="imports-summary">' +
        '<div class="kpi-grid imports-kpis">' +
          '<div class="kpi"><div class="kpi-label">Schedule</div>' +
            '<div class="kpi-value">' +
              (s.schedule_id != null ? '#' + s.schedule_id : '—') +
            '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Rows in file</div>' +
            '<div class="kpi-value">' + fmtNum(s.total_rows) + '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Inserted</div>' +
            '<div class="kpi-value good">' + fmtNum(s.inserted) + '</div></div>' +
          '<div class="kpi"><div class="kpi-label">Skipped</div>' +
            '<div class="kpi-value">' + fmtNum(s.skipped) + '</div></div>' +
        '</div>' +
        '<div class="small">' +
          'Strategy: <code>' + escapeHtml(strategy || 'warn') + '</code>' +
          '  ·  ' + s.duration_ms + ' ms' +
          '  ·  ' + escapeHtml(s.source_file || '') +
        '</div>' +
        conflict +
        (errs ? '<details class="imports-errs"><summary>' +
                  s.errors.length + ' errors</summary><ul>' + errs + '</ul></details>'
              : '') +
      '</div>';
  }

  function renderScheduleGrid(rows) {
    if (!rows || !rows.length) {
      return '<div class="small">No tariff schedules yet — upload one above.</div>';
    }
    var trs = rows.map(function (s) {
      var badge = s.is_active
        ? '<span class="badge ok">active</span>'
        : '<span class="badge muted">inactive</span>';
      var cats = (s.categories || []).join(', ');
      return (
        '<tr data-schedule-id="' + s.id + '">' +
          '<td>' + badge + ' <b>' + escapeHtml(s.schedule_name) + '</b></td>' +
          '<td>' + fmtDate(s.effective_from) + '</td>' +
          '<td>' + fmtDate(s.effective_to)   + '</td>' +
          '<td>' + escapeHtml(cats) + '</td>' +
          '<td class="num">' + fmtNum(s.row_count) + '</td>' +
          '<td>' +
            '<button class="btn small" data-toggle-schedule="' + s.id +
                  '" data-next="' + (s.is_active ? '0' : '1') + '">' +
              (s.is_active ? 'Deactivate' : 'Activate') +
            '</button>' +
          '</td>' +
        '</tr>'
      );
    }).join('');
    return (
      '<table class="data-table">' +
        '<thead><tr>' +
          '<th>Schedule</th><th>Effective From</th><th>Effective To</th>' +
          '<th>Categories</th><th class="num">Rows</th><th></th>' +
        '</tr></thead>' +
        '<tbody>' + trs + '</tbody>' +
      '</table>'
    );
  }

  /** ------------------------------------------------------------- *
   *  Setup entry-point.                                             *
   * ------------------------------------------------------------- */

  function setup() {
    var panel = $('#panel-imports');
    if (!panel) return;
    if (panel.dataset.importsReady === '1') return;
    setupHistoricalCard();
    setupRateCard();
    panel.dataset.importsReady = '1';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
  window.RAID_setupImportsPanel = setup;
})();
