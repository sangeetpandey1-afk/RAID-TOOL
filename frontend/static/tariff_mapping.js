/* ==================================================================
 * Raid Management System — Tariff Mapping (PURE DATA + READ-ONLY API)
 * ------------------------------------------------------------------
 * Single source of truth for:
 *   - the Category dropdown (#f_category) master list
 *   - which Supply Type codes are valid under each Category
 *   - per-supply-type metadata (basis, area, load range) that the
 *     future tariff / calculator / notice-wording engines will
 *     consume *without* duplicating data.
 *
 * SAFETY CONTRACT
 *   - This file contains ONLY data and pure functions.
 *   - It does NOT touch the DOM, fire any network call, or mutate
 *     any global beyond setting `window.RAID_TARIFF_MAPPING`.
 *   - It is loaded BEFORE app.js so existing app.js code (and the
 *     forthcoming tariff engine) can read window.RAID_TARIFF_MAPPING
 *     synchronously.
 *   - Plain ES5-compatible — no build step required.
 *
 * MAINTAINER NOTES
 *   - The supplyTypes lists for LMV-1, LMV-2 and LMV-5 are populated
 *     from the project owner's specification (PR description).
 *   - Categories LMV-3, LMV-4, LMV-6..LMV-11, HV-1..HV-4 currently
 *     carry a single TBD placeholder so the dropdown is never empty.
 *     Replace the placeholder when authoritative tariff codes are
 *     available — the shape of each entry is fixed:
 *
 *         { code, desc, basis, area, loadRange }
 *
 *       basis     ∈ 'KWH' | 'KVAH' | 'BHP' | 'DAYS' | 'TBD'
 *       area      ∈ 'Urban' | 'Rural' | 'Both' | 'TBD'
 *       loadRange — free-form short string ('<10kW', '>=10kW',
 *                   '<7.5BHP', 'Any', 'TBD' …)
 *
 *   - Bumping `version` is optional; it is exported so downstream
 *     caches can detect mapping changes if needed later.
 *
 * BACKEND COMPATIBILITY
 *   - The backend stores `category` and `supply_type` as plain
 *     strings; any code (e.g. '10', '24B', 'OTH') or label string
 *     used here will round-trip unchanged through /api/cases.
 *   - Old cases saved with pre-mapping values ('Domestic',
 *     'Agricultural', 'HV' …) are preserved by category_supply.js's
 *     legacy-option injection on case load.
 * ==================================================================
 */

(function () {
  'use strict';

  /** Build a single placeholder entry for a not-yet-populated category. */
  function tbd(label) {
    return [{
      code: 'TBD',
      desc: label || 'Awaiting tariff data — populate tariff_mapping.js',
      basis: 'TBD',
      area: 'TBD',
      loadRange: 'TBD'
    }];
  }

  var MAPPING = {
    version: '2026-05-22',

    /* Drives the #f_category dropdown — strict order. */
    categories: [
      'LMV-1', 'LMV-2', 'LMV-3', 'LMV-4', 'LMV-5', 'LMV-6',
      'LMV-7', 'LMV-8', 'LMV-9', 'LMV-10', 'LMV-11',
      'HV-1', 'HV-2', 'HV-3', 'HV-4',
      'Other'
    ],

    /* Category -> ordered array of supply-type entries.            *
     * Keep arrays read-only at the call site; getSupplyTypes()     *
     * returns a shallow copy.                                       */
    supplyTypes: {
      'LMV-1': [
        { code: '10',  desc: 'Urban Domestic (<10kW)',     basis: 'KWH',  area: 'Urban', loadRange: '<10kW'  },
        { code: '10A', desc: 'Urban Domestic — BPL',       basis: 'KWH',  area: 'Urban', loadRange: '<10kW'  },
        { code: '11',  desc: 'Urban Domestic (>=10kW)',    basis: 'KVAH', area: 'Urban', loadRange: '>=10kW' },
        { code: '17',  desc: 'Rural Domestic (<10kW)',     basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '17A', desc: 'Rural Domestic — BPL',       basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '18',  desc: 'Rural Domestic (Unmetered)', basis: 'DAYS', area: 'Rural', loadRange: '<10kW'  },
        { code: '19',  desc: 'Rural Domestic (>=10kW)',    basis: 'KVAH', area: 'Rural', loadRange: '>=10kW' }
      ],

      'LMV-2': [
        { code: '20',  desc: 'Commercial Urban (<10kW)',     basis: 'KWH',  area: 'Urban', loadRange: '<10kW'  },
        { code: '22',  desc: 'Commercial Urban (>=10kW)',    basis: 'KVAH', area: 'Urban', loadRange: '>=10kW' },
        { code: '24',  desc: 'Commercial Rural (<10kW)',     basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '24B', desc: 'Commercial Rural — Variant B', basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '24C', desc: 'Commercial Rural — Variant C', basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '24D', desc: 'Commercial Rural — Variant D', basis: 'KWH',  area: 'Rural', loadRange: '<10kW'  },
        { code: '25',  desc: 'Commercial Rural (>=10kW)',    basis: 'KVAH', area: 'Rural', loadRange: '>=10kW' },
        { code: '26',  desc: 'Advertisements / Hoardings',   basis: 'KWH',  area: 'Both',  loadRange: 'Any'    },
        { code: '27',  desc: 'Mixed Commercial Use',         basis: 'KWH',  area: 'Both',  loadRange: 'Any'    },
        { code: '28',  desc: 'Temporary Commercial',         basis: 'KWH',  area: 'Both',  loadRange: 'Any'    }
      ],

      'LMV-3': tbd('Public Lamps — populate from tariff order'),
      'LMV-4': tbd('Public Institutions — populate from tariff order'),

      'LMV-5': [
        { code: '50', desc: 'PTW Urban Metered (<10kW)',     basis: 'KWH',  area: 'Urban', loadRange: '<10kW'   },
        { code: '51', desc: 'PTW Rural Metered (<10kW)',     basis: 'KWH',  area: 'Rural', loadRange: '<10kW'   },
        { code: '52', desc: 'PTW Rural Unmetered (<7.5BHP)', basis: 'BHP',  area: 'Rural', loadRange: '<7.5BHP' },
        { code: '53', desc: 'PTW Rural Metered (>=10kW)',    basis: 'KVAH', area: 'Rural', loadRange: '>=10kW'  },
        { code: '54', desc: 'PTW Mixed / Special',           basis: 'KWH',  area: 'Both',  loadRange: 'Any'     }
      ],

      'LMV-6':  tbd('Small / Medium Industrial — populate from tariff order'),
      'LMV-7':  tbd('Public Water Works / Sewage — populate from tariff order'),
      'LMV-8':  tbd('Private Institutions — populate from tariff order'),
      'LMV-9':  tbd('Temporary Supply — populate from tariff order'),
      'LMV-10': tbd('EV Charging — populate from tariff order'),
      'LMV-11': tbd('Other LMV — populate from tariff order'),

      'HV-1':   tbd('Non-Industrial Bulk — populate from tariff order'),
      'HV-2':   tbd('HV Industrial — populate from tariff order'),
      'HV-3':   tbd('Railway Traction — populate from tariff order'),
      'HV-4':   tbd('Lift Irrigation — populate from tariff order'),

      'Other':  [
        { code: 'OTH', desc: 'Other / Custom — see case notes', basis: 'TBD', area: 'TBD', loadRange: 'Any' }
      ]
    },

    /* ---------- pure read APIs ---------- */

    /** Returns a copy of the master category list. */
    getCategories: function () {
      return this.categories.slice();
    },

    /** Returns a copy of the supply-type entries for `category`,
     *  or [] if the category is unknown.                         */
    getSupplyTypes: function (category) {
      var arr = this.supplyTypes[category];
      return arr ? arr.slice() : [];
    },

    /** Looks up a supply-type entry by its code anywhere in the
     *  mapping; returns the entry plus its parent category, or null. */
    findSupplyTypeByCode: function (code) {
      if (!code) return null;
      for (var cat in this.supplyTypes) {
        if (!this.supplyTypes.hasOwnProperty(cat)) continue;
        var list = this.supplyTypes[cat];
        for (var i = 0; i < list.length; i++) {
          if (list[i].code === code) {
            var copy = {};
            for (var k in list[i]) {
              if (list[i].hasOwnProperty(k)) copy[k] = list[i][k];
            }
            copy.category = cat;
            return copy;
          }
        }
      }
      return null;
    },

    /** Canonical dropdown label: "CODE — DESC". */
    formatLabel: function (entry) {
      if (!entry) return '';
      return entry.code + ' — ' + entry.desc;
    }
  };

  window.RAID_TARIFF_MAPPING = MAPPING;
})();
