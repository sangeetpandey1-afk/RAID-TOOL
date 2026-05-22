/* ==================================================================
   Raid Management System — mobile UX enhancements (ADDITIVE)
   ------------------------------------------------------------------
   Loaded AFTER app.js. Pure progressive enhancement:
     - Injects hamburger button + backdrop into the existing topbar
     - Toggles body.nav-open (CSS handles slide-in drawer)
     - Auto-closes drawer when a tab is tapped (existing app.js
       handler still runs because we don't stopPropagation)
     - Marks Raid Master / cases tables with .table-cards on phones
       and injects data-label attributes onto <td> cells so CSS can
       render them as stacked cards.
     - Marks the New Case primary action bar as .sticky-mobile.

   Does NOT modify any existing JS, routes, business logic or
   form structure. Safe to load on desktop — every operation
   is feature-detected and idempotent.
   ================================================================== */
(function () {
  'use strict';

  var MOBILE_MAX = 768;
  var isPhone = function () {
    return window.matchMedia('(max-width: ' + MOBILE_MAX + 'px)').matches;
  };

  // ----------------------------------------------------------------
  // 1. HAMBURGER + BACKDROP
  // ----------------------------------------------------------------
  function injectHamburger() {
    var topbar = document.querySelector('.topbar');
    if (!topbar || topbar.querySelector('.hamburger')) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'hamburger';
    btn.setAttribute('aria-label', 'Toggle navigation');
    btn.setAttribute('aria-controls', 'tabs');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<span class="bar"></span><span class="bar"></span><span class="bar"></span>';
    topbar.insertBefore(btn, topbar.firstChild);

    var backdrop = document.createElement('div');
    backdrop.className = 'nav-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);

    function setOpen(open) {
      document.body.classList.toggle('nav-open', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      setOpen(!document.body.classList.contains('nav-open'));
    });

    backdrop.addEventListener('click', function () { setOpen(false); });

    // Close drawer when any tab is tapped (existing tab handler still fires)
    var tabsBar = document.getElementById('tabs');
    if (tabsBar) {
      tabsBar.addEventListener('click', function (e) {
        if (e.target && e.target.classList && e.target.classList.contains('tab')) {
          setOpen(false);
        }
      });
    }

    // Close drawer on resize back to desktop
    window.addEventListener('resize', function () {
      if (!isPhone()) setOpen(false);
    });

    // Close on Escape for keyboard users
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('nav-open')) {
        setOpen(false);
      }
    });
  }

  // ----------------------------------------------------------------
  // 2. STICKY MOBILE ACTION BAR — for the New Case primary actions
  //    (the actions-row that contains "Save Case")
  // ----------------------------------------------------------------
  function markStickyActionBars() {
    var saveBtn = document.querySelector('[data-action="save-case"]');
    if (saveBtn) {
      var row = saveBtn.closest('.actions-row');
      if (row) row.classList.add('sticky-mobile');
    }
  }

  // ----------------------------------------------------------------
  // 3. TABLE-AS-CARDS ON PHONES
  //    For each table marked in CARD_TABLES, inject data-label on
  //    <td> cells (matching the corresponding <th>) and toggle the
  //    .table-cards class only when on phone width. CSS does the rest.
  // ----------------------------------------------------------------
  var CARD_TABLES = [
    { id: 'casesTable',   actionsLastCol: true },
    { id: 'searchTable',  actionsLastCol: true },
    { id: 'paymentsTable', actionsLastCol: false },
    { id: 'noticesTable', actionsLastCol: false },
    { id: 'backupTable',  actionsLastCol: true },
    { id: 'reportsTable', actionsLastCol: true },
    { id: 'caseDocsTable', actionsLastCol: true }
  ];

  function getHeaderLabels(table) {
    var ths = table.querySelectorAll('thead th');
    var labels = [];
    for (var i = 0; i < ths.length; i++) {
      labels.push((ths[i].textContent || '').trim());
    }
    return labels;
  }

  function decorateRow(tr, labels, actionsLastCol) {
    var tds = tr.children;
    for (var i = 0; i < tds.length; i++) {
      var td = tds[i];
      if (td.tagName !== 'TD') continue;
      var label = labels[i] || '';
      // Only set if not already set (idempotent)
      if (!td.hasAttribute('data-label')) {
        td.setAttribute('data-label', label);
      }
      // Mark last column as actions if requested and it contains a button
      if (actionsLastCol && i === tds.length - 1 && td.querySelector('.btn')) {
        td.classList.add('actions-col');
      }
      // Detect "num" alignment from <th> class
      // (existing styles already set .num via thead — copy to td)
    }
  }

  function decorateTable(spec) {
    var table = document.getElementById(spec.id);
    if (!table) return;
    var labels = getHeaderLabels(table);
    if (!labels.length) return;

    // Decorate existing rows
    var rows = table.querySelectorAll('tbody tr');
    for (var i = 0; i < rows.length; i++) {
      decorateRow(rows[i], labels, spec.actionsLastCol);
    }

    // Watch for dynamically-added rows (existing app.js renders via innerHTML)
    var tbody = table.querySelector('tbody');
    if (tbody && !tbody._mobileObserver) {
      var obs = new MutationObserver(function () {
        var newRows = tbody.querySelectorAll('tr');
        for (var j = 0; j < newRows.length; j++) {
          decorateRow(newRows[j], labels, spec.actionsLastCol);
        }
      });
      obs.observe(tbody, { childList: true, subtree: false });
      tbody._mobileObserver = obs;
    }
  }

  function applyTableMode() {
    var phone = isPhone();
    for (var i = 0; i < CARD_TABLES.length; i++) {
      var t = document.getElementById(CARD_TABLES[i].id);
      if (!t) continue;
      t.classList.toggle('table-cards', phone);
    }
  }

  function setupTables() {
    for (var i = 0; i < CARD_TABLES.length; i++) {
      decorateTable(CARD_TABLES[i]);
    }
    applyTableMode();
    window.addEventListener('resize', debounce(applyTableMode, 150));
  }

  // ----------------------------------------------------------------
  // 4. UTIL
  // ----------------------------------------------------------------
  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  // ----------------------------------------------------------------
  // BOOT
  // ----------------------------------------------------------------
  function boot() {
    try {
      injectHamburger();
      markStickyActionBars();
      setupTables();
    } catch (err) {
      // Never break the existing UI — log only
      if (window.console) console.warn('[mobile.js] boot error:', err);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
