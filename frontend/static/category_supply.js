/* ==================================================================
 * Raid Management System — Category ↔ Supply Type linkage (DOM glue)
 * ------------------------------------------------------------------
 * Wires the New Case form's #f_category and #f_supply selects to the
 * data declared in window.RAID_TARIFF_MAPPING (tariff_mapping.js).
 *
 * RESPONSIBILITIES
 *   1. On DOMContentLoaded:
 *        - Replace the static #f_category options with the master
 *          category list.
 *        - Populate #f_supply with the supply-type entries of the
 *          currently selected category (default: first entry,
 *          LMV-1).
 *   2. On user change of #f_category:
 *        - Repopulate #f_supply with the matching list.
 *   3. On programmatic value assignment (case load via app.js):
 *        - Override the per-element .value setter on #f_category so
 *          that `setIf("#f_category", "LMV-3")` (or
 *          `ensureCategoryOption("LMV-3")` in app.js) immediately
 *          repopulates #f_supply *synchronously*. This way the
 *          NEXT line in app.js — `$("#f_supply").value = c.supply_type;`
 *          — sees the correct option list.
 *        - Override the per-element .value setter on #f_supply so
 *          that an unknown legacy value (e.g. "Domestic" from a
 *          pre-mapping saved case) is preserved by injecting a
 *          `<option value="Domestic">Domestic (legacy)</option>`
 *          rather than being silently dropped.
 *
 * SAFETY CONTRACT
 *   - Does NOT modify app.js, mobile.js, mobile.css, styles.css, or
 *     any backend file.
 *   - Does NOT change save payload shape: backend still receives
 *     plain string `category` and `supply_type` values (the codes
 *     "10", "24B", or legacy strings round-trip unchanged).
 *   - Does NOT alter calculation, notice-generation, or LFHD logic.
 *   - Idempotent: re-running setupLinkage() is a no-op.
 *   - Defensive: if tariff_mapping.js failed to load or the form
 *     elements are missing, this script logs a warning and exits;
 *     the original static <option> set in index.html remains usable.
 *
 * SCRIPT ORDER (index.html)
 *
 *     <script src="/frontend/static/tariff_mapping.js"></script>
 *     <script src="/frontend/static/category_supply.js"></script>
 *     <script src="/frontend/static/app.js"></script>
 *
 *   Both DOMContentLoaded handlers (this file's and app.js's) fire
 *   in registration order, so #f_category options and the .value
 *   setter overrides are in place BEFORE app.js's load handler runs.
 * ==================================================================
 */

(function () {
  'use strict';

  /** ------------------------------------------------------------- *
   *  Tiny DOM helpers — no dependencies on app.js or jQuery.        *
   * ------------------------------------------------------------- */

  function $(sel) { return document.querySelector(sel); }

  function clearOptions(sel) {
    while (sel.firstChild) sel.removeChild(sel.firstChild);
  }

  function makeOption(value, label, isLegacy) {
    var opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    if (isLegacy) {
      opt.dataset.legacy = '1';
      // amber so the operator notices the value came from an
      // older saved case and may want to re-pick a current code.
      opt.style.color = '#92400e';
    }
    return opt;
  }

  function optionExists(sel, value) {
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === value) return true;
    }
    return false;
  }

  /** ------------------------------------------------------------- *
   *  Category dropdown — replace static options with master list.  *
   * ------------------------------------------------------------- */

  function populateCategories(catSel, mapping) {
    var preserved = catSel.value;
    clearOptions(catSel);
    mapping.getCategories().forEach(function (c) {
      catSel.appendChild(makeOption(c, c, false));
    });
    // If the previously selected category is still in the master
    // list, keep it; otherwise leave the first option (LMV-1) selected.
    if (preserved && mapping.getCategories().indexOf(preserved) !== -1) {
      catSel.value = preserved;
    }
  }

  /** ------------------------------------------------------------- *
   *  Supply Type dropdown — populate based on a category value.    *
   *                                                                 *
   *  Each <option> stashes the supply-type metadata as data-*       *
   *  attributes so the future tariff/calculator engine can read    *
   *  them straight from the selected option — no extra lookup,     *
   *  no second source of truth.                                    *
   * ------------------------------------------------------------- */

  function populateSupplyTypes(supplySel, category, mapping) {
    var entries = mapping.getSupplyTypes(category);
    clearOptions(supplySel);

    if (entries.length === 0) {
      // Defensive — should not happen because every category has at
      // least a TBD entry, but if the mapping is ever truncated we
      // still want a usable, non-empty select.
      supplySel.appendChild(makeOption('', '— select —', false));
      return;
    }

    entries.forEach(function (e) {
      var opt = makeOption(e.code, mapping.formatLabel(e), false);
      opt.dataset.basis     = e.basis;
      opt.dataset.area      = e.area;
      opt.dataset.loadRange = e.loadRange;
      supplySel.appendChild(opt);
    });
  }

  /** ------------------------------------------------------------- *
   *  Patch a select's .value setter (per-element, not prototype).  *
   *                                                                 *
   *  - For #f_category: also repopulate #f_supply on every          *
   *    programmatic assignment, so app.js's two-line                *
   *      ensureCategoryOption(c.category);                          *
   *      $("#f_supply").value = c.supply_type;                      *
   *    pattern works without modification.                         *
   *                                                                 *
   *  - For #f_supply: inject a (legacy) option when an unknown     *
   *    value is assigned, so saved cases pre-dating this mapping   *
   *    (Domestic / Commercial / Industrial / Agricultural) keep    *
   *    round-tripping their original supply_type string.           *
   *                                                                 *
   *  Native getter/setter live on HTMLSelectElement.prototype; we  *
   *  install our own own-property accessor on the element so       *
   *  `.value` reads/writes go through us first, then delegate to   *
   *  the native descriptor.                                        *
   * ------------------------------------------------------------- */

  function patchValueSetter(sel, opts) {
    opts = opts || {};
    var afterSet     = opts.afterSet     || null;
    var injectLegacy = opts.injectLegacy === true;
    var legacyAtTop  = opts.legacyAtTop  === true;

    var nativeDesc = Object.getOwnPropertyDescriptor(
      HTMLSelectElement.prototype, 'value'
    );
    if (!nativeDesc || !nativeDesc.set || !nativeDesc.get) {
      // Truly unexpected — keep static behaviour rather than break.
      return;
    }

    Object.defineProperty(sel, 'value', {
      configurable: true,
      enumerable: true,
      get: function () {
        return nativeDesc.get.call(this);
      },
      set: function (v) {
        if (injectLegacy && v != null && v !== '' && !optionExists(this, v)) {
          var legacy = makeOption(String(v), String(v) + ' (legacy)', true);
          if (legacyAtTop) {
            this.insertBefore(legacy, this.firstChild);
          } else {
            this.appendChild(legacy);
          }
        }
        nativeDesc.set.call(this, v);
        if (typeof afterSet === 'function') {
          afterSet.call(this, v);
        }
      }
    });
  }

  /** ------------------------------------------------------------- *
   *  Main wiring.                                                   *
   * ------------------------------------------------------------- */

  function setupLinkage() {
    var mapping = window.RAID_TARIFF_MAPPING;
    if (!mapping) {
      console.warn(
        '[category_supply] window.RAID_TARIFF_MAPPING not loaded; ' +
        'leaving static <option> list in place.'
      );
      return;
    }

    var catSel    = $('#f_category');
    var supplySel = $('#f_supply');
    if (!catSel || !supplySel) {
      // The New Case panel may have been re-laid-out; fail closed.
      return;
    }

    // Idempotency guard — safe to call setupLinkage() multiple times.
    if (catSel.dataset.linkageReady === '1') return;

    /* ---- 1. Hydrate options from the mapping. ---- */
    populateCategories(catSel, mapping);
    populateSupplyTypes(supplySel, catSel.value, mapping);

    /* ---- 2. User-driven changes. ---- *
     * The browser fires native 'change' on user interaction (mouse,
     * keyboard, touch); programmatic .value = … does NOT fire it,
     * so this listener handles ONLY the user path. The setter
     * patch below handles the programmatic path.                  */
    catSel.addEventListener('change', function () {
      populateSupplyTypes(supplySel, catSel.value, mapping);
    });

    /* ---- 3. Programmatic round-trip safety. ---- *
     * Patches MUST be installed AFTER the populate* calls above
     * so the initial hydration uses the native fast path.          */
    patchValueSetter(catSel, {
      injectLegacy: true,
      legacyAtTop:  false,           // legacies appended at end of master list
      afterSet: function (newCategory) {
        // Repopulate supply synchronously; if newCategory is unknown
        // the supply list collapses to the defensive '— select —'
        // option and the supply patch below will inject any legacy
        // supply_type value on its next assignment.
        populateSupplyTypes(supplySel, newCategory, mapping);
      }
    });

    patchValueSetter(supplySel, {
      injectLegacy: true,
      legacyAtTop:  true             // legacies prepended so they're visible first
    });

    catSel.dataset.linkageReady = '1';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupLinkage);
  } else {
    setupLinkage();
  }

  /* Expose a manual hook so a console operator (or future code that
   * rebuilds the form) can re-run the wiring without a full reload. */
  window.RAID_setupCategorySupply = setupLinkage;
})();
