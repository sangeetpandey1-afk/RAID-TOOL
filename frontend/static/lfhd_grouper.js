/* ==================================================================
 * Raid Management System — Grouped LFHD formatter (frontend)
 * ------------------------------------------------------------------
 * Reusable helper that:
 *
 *   1. Groups device rows by (hours, factor, days) — devices that
 *      share the same H/F/D collapse into a single row whose load is
 *      the SUM of the contributing devices' loads.
 *   2. Formats each group as the legal-style math line
 *           L × H × F × D = Units
 *      (Load shown in kW, Units in kWh, two decimals trimmed.)
 *   3. Renders the grouped output as HTML for the New Case panel
 *      and as plain text for clipboard / future PDF / future notices.
 *
 * SCOPE  (this PR is intentionally additive)
 *   - Frontend only: nothing here changes how the LFHD calculator
 *     runs, how cases are saved, or how notices are generated today.
 *   - The same logic is mirrored in `backend/services/lfhd_grouper.py`
 *     so that existing notice templates can be opted-in to the new
 *     grouped output one at a time, in a separate PR, after each
 *     template's wording has been reviewed by the project owner.
 *
 * SAFETY CONTRACT
 *   - Does NOT modify app.js. Hooks into the existing #devicesBody
 *     entirely via event delegation + MutationObserver.
 *   - Does NOT modify the device payload sent to the backend.
 *     `collectDevicesFromUI` in app.js still produces the same
 *     shape; this module only READS the form state.
 *   - Does NOT change the existing Total Connected Load auto-sum
 *     logic. That uses Watts; this module reads the same Watts and
 *     converts to kW only for printed output.
 *   - Idempotent setup; safe across hot-reload.
 *
 * INPUT  (from #devicesBody — same shape app.js builds rows from)
 *
 *     {
 *       name:    string,
 *       load:    number,   // Watts (Section 4 column header is "Load (W)")
 *       factor:  number,   // dimensionless 0..1
 *       hours:   number,   // hours/day
 *       days:    number    // days
 *     }
 *
 * GROUP OUTPUT
 *
 *     {
 *       loadKW:      number,   // sum of contributing loads ÷ 1000
 *       hours:       number,
 *       factor:      number,
 *       days:        number,
 *       units:       number,   // loadKW × hours × factor × days
 *       deviceCount: number,
 *       deviceNames: string[]
 *     }
 *
 * MATH STRING FORMAT — matches the project owner's spec exactly:
 *
 *     "0.3 × 18 × 0.3 × 365 = 591.3"
 *
 *   Numbers are formatted to up to 3 decimals (load) / 2 decimals
 *   (others) and then stripped of trailing zeros so the math reads
 *   cleanly on a printed legal page.
 * ==================================================================
 */

(function () {
  'use strict';

  /* ------------------------------------------------------------- *
   *  Pure helpers — no DOM, deterministic, testable in isolation.  *
   * ------------------------------------------------------------- */

  /** Trim trailing zeros after toFixed: 0.300 -> "0.3", 365 -> "365". */
  function trim(n, decimals) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    var fixed = Number(n).toFixed(decimals);
    // parseFloat eats the trailing zeros; toString gives canonical form.
    return parseFloat(fixed).toString();
  }

  /** Round to N decimals (avoids fp surprise like 0.1 + 0.2 = 0.30000…). */
  function round(n, decimals) {
    var p = Math.pow(10, decimals);
    return Math.round(Number(n) * p) / p;
  }

  /** Build the (hours, factor, days) bucket key. Rounding kills
   *  spurious float noise so e.g. 0.3 typed twice always groups.    */
  function bucketKey(d) {
    return [
      round(d.hours,  3),
      round(d.factor, 3),
      round(d.days,   0)
    ].join('|');
  }

  /** Return only rows that have non-zero numeric values for L/H/F/D.
   *  An empty or partial row should not appear in printed math.     */
  function isValidDevice(d) {
    var L = Number(d.load),   H = Number(d.hours);
    var F = Number(d.factor), D = Number(d.days);
    return (
      isFinite(L) && L > 0 &&
      isFinite(H) && H > 0 &&
      isFinite(F) && F > 0 &&
      isFinite(D) && D > 0
    );
  }

  /**
   * Group an array of device rows by identical (hours, factor, days)
   * and sum their loads. Order of groups matches first-occurrence in
   * input. Returns a NEW array — input is never mutated.
   */
  function group(devices) {
    if (!Array.isArray(devices)) return [];
    var order   = [];
    var buckets = Object.create(null);

    devices.forEach(function (d) {
      if (!isValidDevice(d)) return;
      var key = bucketKey(d);
      if (!buckets[key]) {
        order.push(key);
        buckets[key] = {
          loadW:       0,                       // accumulator in Watts
          hours:       round(Number(d.hours),  3),
          factor:      round(Number(d.factor), 3),
          days:        round(Number(d.days),   0),
          deviceNames: []
        };
      }
      var b = buckets[key];
      b.loadW += Number(d.load);
      b.deviceNames.push(String(d.name || '').trim() || '(unnamed)');
    });

    return order.map(function (k) {
      var b = buckets[k];
      var loadKW = b.loadW / 1000;
      return {
        loadKW:      round(loadKW, 4),
        hours:       b.hours,
        factor:      b.factor,
        days:        b.days,
        units:       round(loadKW * b.hours * b.factor * b.days, 3),
        deviceCount: b.deviceNames.length,
        deviceNames: b.deviceNames.slice()
      };
    });
  }

  /** "0.3 × 18 × 0.3 × 365 = 591.3" — the canonical legal math line. */
  function formatMath(g) {
    return (
      trim(g.loadKW, 3) + ' × ' +
      trim(g.hours,  2) + ' × ' +
      trim(g.factor, 3) + ' × ' +
      trim(g.days,   0) + ' = ' +
      trim(g.units,  2)
    );
  }

  /** Sum of group units. */
  function totalUnits(groups) {
    return round(
      (groups || []).reduce(function (s, g) { return s + g.units; }, 0),
      3
    );
  }

  /** ------------------------------------------------------------- *
   *  Renderers — return strings; the DOM glue below decides where  *
   *  to insert them. Keeping them as pure string returners means    *
   *  the same module can later feed the print preview, a clipboard *
   *  copy action, or a future PDF generator unchanged.             *
   * ------------------------------------------------------------- */

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c];
    });
  }

  /** HTML for embedding in the New Case panel. */
  function renderHtml(devices) {
    var groups = group(devices);
    if (groups.length === 0) {
      return '<div class="lfhd-empty small">' +
             'Fill in Load, Factor, Hours and Days for at least one device ' +
             'to see the grouped LFHD math.</div>';
    }
    var rows = groups.map(function (g, i) {
      var names = g.deviceNames.length === 1
        ? escapeHtml(g.deviceNames[0])
        : g.deviceNames.map(escapeHtml).join(', ') +
          ' <span class="small">(' + g.deviceCount + ' devices)</span>';
      return (
        '<li>' +
          '<code class="lfhd-math">' + escapeHtml(formatMath(g)) + '</code> ' +
          '<span class="lfhd-units small">Units</span>' +
          '<div class="lfhd-devices small">' + names + '</div>' +
        '</li>'
      );
    }).join('');
    var total = trim(totalUnits(groups), 2);
    return (
      '<ol class="lfhd-rows">' + rows + '</ol>' +
      '<div class="lfhd-total"><b>Total Units</b> = ' +
        '<code>' + escapeHtml(total) + '</code></div>'
    );
  }

  /** Plain-text version (for clipboard / future PDF / future notice). */
  function renderText(devices) {
    var groups = group(devices);
    if (groups.length === 0) return '(no LFHD entries)';
    var lines = groups.map(function (g, i) {
      return (i + 1) + '. ' + formatMath(g) + ' Units';
    });
    lines.push('');
    lines.push('Total Units = ' + trim(totalUnits(groups), 2));
    return lines.join('\n');
  }

  /** ------------------------------------------------------------- *
   *  Public namespace — usable from console / future tariff engine *
   *  / future export-to-PDF code without re-importing.             *
   * ------------------------------------------------------------- */

  var API = {
    group:        group,
    formatMath:   formatMath,
    totalUnits:   totalUnits,
    renderHtml:   renderHtml,
    renderText:   renderText
  };

  window.RAID_LFHD = API;

  /* =============================================================== *
   *  DOM glue — the rest of this file is the page integration.      *
   *  Everything above this line is pure logic and re-usable.        *
   * =============================================================== */

  var DEVICE_PRESETS = [
    'Bulb / LED',
    'Ceiling Fan',
    'Cooler',
    'AC',
    'Refrigerator',
    'Submersible',
    'Heater / Geyser',
    'Washing Machine',
    'Iron Press',
    'Induction'
  ];

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  /** Read the live device table and convert each row to the
   *  shape `group()` expects. We deliberately read the DOM rather
   *  than reach into app.js's STATE.devices — that keeps this module
   *  independent of app.js internals. Empty / non-numeric cells are
   *  treated as zero so partially-filled rows are silently dropped
   *  by isValidDevice() inside group().                              */
  function readDevicesFromDom() {
    return $$('#devicesBody tr').map(function (tr) {
      function v(field) {
        var inp = tr.querySelector('input[data-field="' + field + '"]');
        return inp ? inp.value : '';
      }
      return {
        name:   v('name'),
        load:   Number(v('load'))   || 0,
        factor: Number(v('factor')) || 0,
        hours:  Number(v('hours'))  || 0,
        days:   Number(v('days'))   || 0
      };
    });
  }

  /** Add `list="device-presets"` to every Device-name input that
   *  doesn't already have it. Runs every time the device table
   *  changes — lets app.js render rows however it likes; this just
   *  decorates them progressively.                                   */
  function annotateDeviceInputs() {
    $$('#devicesBody input[data-field="name"]').forEach(function (inp) {
      if (inp.getAttribute('list') !== 'device-presets') {
        inp.setAttribute('list', 'device-presets');
      }
    });
  }

  /** Re-render the LFHD summary card from the live DOM. */
  function refreshSummary() {
    var card = $('#lfhdSummary');
    if (!card) return;
    card.innerHTML = renderHtml(readDevicesFromDom());
  }

  /** Inject the <datalist> with the preset device names. We do this
   *  in JS (rather than in index.html) so the preset list lives in
   *  exactly one place — this file. To extend, edit DEVICE_PRESETS.  */
  function ensureDatalist() {
    if (document.getElementById('device-presets')) return;
    var dl = document.createElement('datalist');
    dl.id = 'device-presets';
    DEVICE_PRESETS.forEach(function (p) {
      var o = document.createElement('option');
      o.value = p;
      dl.appendChild(o);
    });
    document.body.appendChild(dl);
  }

  function setup() {
    var body = $('#devicesBody');
    var card = $('#lfhdSummary');
    if (!body || !card) return;       // panel not present — nothing to do
    if (body.dataset.lfhdReady === '1') return;   // idempotent

    ensureDatalist();
    annotateDeviceInputs();
    refreshSummary();

    /* Live updates as the operator types — delegated input listener. */
    body.addEventListener('input', refreshSummary);

    /* Row added or removed by app.js (it sets innerHTML wholesale).   *
     * Use a MutationObserver because we don't want to monkey-patch    *
     * app.js's renderDevices(). On every structural change we both   *
     * re-annotate and re-render the summary.                         */
    var mo = new MutationObserver(function () {
      annotateDeviceInputs();
      refreshSummary();
    });
    mo.observe(body, { childList: true, subtree: true });

    /* "+ Add Device" / "+ Sample Devices" / "Live Calculate" all     *
     * eventually mutate #devicesBody, which the observer catches —   *
     * but Live Calculate also updates Units cells via setting        *
     * STATE.devices[i].units and re-rendering. The observer covers   *
     * that too. No extra wiring needed.                              */

    body.dataset.lfhdReady = '1';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }

  /* Manual hook so a console operator (or future code that rebuilds *
   * the New Case panel) can re-run wiring without a full reload.    */
  window.RAID_setupLfhdSummary = setup;
})();
