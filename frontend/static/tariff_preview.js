/* ==================================================================
 * Raid Management System — Live Tariff Preview card.
 * ------------------------------------------------------------------
 * On the New Case panel, watches changes to:
 *
 *      #f_category, #f_subcategory, #f_supply, #f_load,
 *      #f_inspection
 *
 * and queries `GET /api/rates/preview` to display the applicable
 * tariff inside the #tariffPreview card.  Lookup is debounced so
 * fast typing in the load field doesn't spam the backend.
 *
 * Safety contract
 * ---------------
 * - Pure additive: does NOT modify app.js, the calculator, the LFHD
 *   grouper, or the case payload.  This card is purely informational.
 * - Read-only against the backend (only GETs).
 * - Idempotent: setup() can be invoked multiple times.
 * - When no schedules / no matching rate, the card shows a soft
 *   message rather than an error.  Operators on first install see
 *   "Upload a tariff schedule on the Imports tab." and can carry
 *   on with the rest of the form unaffected.
 * ================================================================== */

(function () {
  'use strict';

  var DEBOUNCE_MS = 250;

  function $(s) { return document.querySelector(s); }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;',
                '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function fmtMoney(v) {
    if (v == null || v === '') return '—';
    var n = Number(v);
    if (!isFinite(n)) return '—';
    return '\u20B9' + n.toFixed(2);   // ₹
  }

  function readForm() {
    var category    = ($('#f_category')    || {}).value || '';
    var subcategory = ($('#f_subcategory') || {}).value || '';
    var supply      = ($('#f_supply')      || {}).value || '';
    var load        = ($('#f_load')        || {}).value || '';
    var date        = ($('#f_inspection')  || {}).value || '';
    return {
      category:    category.trim(),
      subcategory: subcategory.trim(),
      supply_type: supply.trim(),
      load_kw:     load.trim(),
      on_date:     date.trim(),
    };
  }

  function buildQuery(state) {
    var q = [];
    if (state.category)    q.push('category='    + encodeURIComponent(state.category));
    if (state.subcategory) q.push('subcategory=' + encodeURIComponent(state.subcategory));
    if (state.supply_type) q.push('supply_type=' + encodeURIComponent(state.supply_type));
    if (state.load_kw)     q.push('load_kw='     + encodeURIComponent(state.load_kw));
    if (state.on_date)     q.push('on_date='     + encodeURIComponent(state.on_date));
    return q.join('&');
  }

  function render(card, state, env) {
    if (!card) return;
    if (!state.category) {
      card.innerHTML = '<div class="small tariff-empty">' +
        'Pick a Category (and optionally a Subcategory) to see the ' +
        'applicable tariff for the inspection date.' +
        '</div>';
      return;
    }
    if (!env || !env.ok) {
      card.innerHTML = '<div class="tariff-err">' +
        escapeHtml((env && env.error) || 'Lookup failed') + '</div>';
      return;
    }
    var data = env.data || {};
    if (!data.applicable) {
      card.innerHTML =
        '<div class="tariff-empty small">' +
          escapeHtml(data.message ||
            'No matching tariff. Upload a schedule on the Imports tab.') +
        '</div>';
      return;
    }
    var r = data.applicable;
    var subcat = r.subcategory ? ' ' + escapeHtml(r.subcategory) : '';
    var supply = r.supply_type ? ' · ' + escapeHtml(r.supply_type) : '';
    var loadBand = '';
    if (r.load_from != null || r.load_to != null) {
      loadBand = ' · load ' +
        (r.load_from != null ? r.load_from : '0') + '–' +
        (r.load_to   != null ? r.load_to   : '∞') + ' kW';
    }
    var slabBand = '';
    if (r.unit_from != null || r.unit_to != null) {
      slabBand = ' · units ' +
        (r.unit_from != null ? r.unit_from : '0') + '–' +
        (r.unit_to   != null ? r.unit_to   : '∞');
    }
    card.innerHTML =
      '<div class="tariff-preview-grid">' +
        '<div class="tp-col">' +
          '<div class="tp-label">Applicable Tariff</div>' +
          '<div class="tp-value">' + escapeHtml(r.category) + subcat + supply + '</div>' +
          '<div class="tp-sub small">' + loadBand + slabBand + '</div>' +
        '</div>' +
        '<div class="tp-col">' +
          '<div class="tp-label">Rate</div>' +
          '<div class="tp-value rate">' + fmtMoney(r.energy_charge) +
            '<span class="small"> / unit</span></div>' +
          '<div class="tp-sub small">' +
            (r.fixed_charge   ? 'Fixed ' + fmtMoney(r.fixed_charge) + '   ' : '') +
            (r.duty_percent   ? 'Duty '  + r.duty_percent + '%' : '') +
          '</div>' +
        '</div>' +
        '<div class="tp-col">' +
          '<div class="tp-label">Schedule</div>' +
          '<div class="tp-value">' + escapeHtml(r.schedule_name || '—') + '</div>' +
          '<div class="tp-sub small">Effective ' +
            escapeHtml(r.effective_from || '—') + ' → ' +
            escapeHtml(r.effective_to   || '—') + '</div>' +
        '</div>' +
      '</div>';
  }

  function setup() {
    var card = document.getElementById('tariffPreview');
    if (!card) return;
    if (card.dataset.tariffPreviewReady === '1') return;
    card.dataset.tariffPreviewReady = '1';

    var timer = null;
    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(refresh, DEBOUNCE_MS);
    }
    function refresh() {
      var state = readForm();
      if (!state.category) {
        render(card, state, null);
        return;
      }
      var url = '/api/rates/preview?' + buildQuery(state);
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (env) { render(card, state, env); })
        .catch(function (err) {
          render(card, state, { ok: false, error: err.message || String(err) });
        });
    }

    ['#f_category', '#f_subcategory', '#f_supply',
     '#f_load',     '#f_inspection'].forEach(function (sel) {
      var el = document.querySelector(sel);
      if (!el) return;
      el.addEventListener('change', schedule);
      el.addEventListener('input',  schedule);
    });

    // Initial render — defers slightly so category_supply.js gets to
    // populate the dropdowns first on cold load.
    setTimeout(refresh, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
  window.RAID_setupTariffPreview = setup;
})();
