/* ==================================================================
 * Raid Management System — Tariff dropdowns + live preview (PR3).
 *
 * Behaviour
 * ---------
 * 1. On page load, fetches /api/rates/categories. If the backend
 *    returns at least one category, the static <option>s in
 *    #f_category are REPLACED with the dynamic list. If none come
 *    back (no tariff schedule uploaded yet), the existing static
 *    options remain — guaranteeing the legacy form still works.
 *
 * 2. When #f_category changes, fetch
 *    /api/rates/subcategories?category=… and repopulate #f_subcategory.
 *
 * 3. When #f_subcategory or #f_inspection changes, fetch
 *    /api/rates/preview and render the slab table + metadata.
 *
 * 4. Auto-derives a Supply Type value from the chosen condition_load
 *    so save_case() (in app.js) keeps sending a non-empty value:
 *      domestic    -> Domestic
 *      commercial  -> Commercial
 *      industrial  -> Industrial
 *      agriculture -> Agricultural
 *    Anything else falls back to the existing #f_supply value
 *    (operator can still type/pick manually).
 *
 * Preserves
 * ---------
 * * Reuses API / $ / $$ / toast / escapeHtml / STATE from app.js.
 * * Does NOT redefine any existing handler.
 * * Does NOT remove the Supply Type <select> — only hides its label
 *   via tariff.css; the value stays in the saved payload.
 * ================================================================== */

(function () {
  "use strict";

  // ---- Helpers ---------------------------------------------------
  function setOptions(selectEl, items, currentValue) {
    if (!selectEl) return;
    const prev = currentValue !== undefined ? currentValue : selectEl.value;
    selectEl.innerHTML = items.map(it => {
      const v = it.value === null || it.value === undefined ? "" : it.value;
      const lbl = it.label !== undefined ? it.label : v;
      const sel = String(v) === String(prev) ? " selected" : "";
      return `<option value="${escapeHtml(v)}"${sel}>${escapeHtml(lbl)}</option>`;
    }).join("");
  }

  // Map condition_load -> visible Supply Type option.
  // Falls back to the user's existing choice if no mapping fits.
  const SUPPLY_MAP = {
    "domestic":     "Domestic",
    "household":    "Domestic",
    "residential":  "Domestic",
    "commercial":   "Commercial",
    "shop":         "Commercial",
    "office":       "Commercial",
    "industrial":   "Industrial",
    "industry":     "Industrial",
    "manufacturing":"Industrial",
    "agriculture":  "Agricultural",
    "agricultural": "Agricultural",
    "farm":         "Agricultural",
  };

  function syncSupplyType(condLoad) {
    const supply = $("#f_supply");
    if (!supply || !condLoad) return;
    const target = SUPPLY_MAP[String(condLoad).trim().toLowerCase()];
    if (!target) return;
    // Make sure the option exists, then select it
    const existing = Array.from(supply.options).find(
      o => o.value === target || o.text === target);
    if (existing) {
      supply.value = existing.value || existing.text;
    } else {
      const opt = document.createElement("option");
      opt.text = opt.value = target;
      supply.appendChild(opt);
      supply.value = target;
    }
  }

  // ---- Categories ------------------------------------------------
  let _categoriesLoaded = false;

  async function loadCategories() {
    const sel = $("#f_category");
    if (!sel) return;
    const env = await API.get("/api/rates/categories");
    if (!env.ok) return;  // keep static fallback options
    const list = (env.data && env.data.categories) || [];
    if (!list.length) return;
    const items = list.map(c => ({
      value: c.category,
      label: c.category + (c.subcategory_count > 1
                            ? ` · ${c.subcategory_count} subcats` : ""),
    }));
    setOptions(sel, items, sel.value);
    _categoriesLoaded = true;
    // Cascade once on initial load
    await loadSubcategories(sel.value);
  }

  // ---- Subcategories ---------------------------------------------
  async function loadSubcategories(category) {
    const sub = $("#f_subcategory");
    if (!sub) return;
    if (!category) {
      sub.innerHTML = `<option value="">(any load band)</option>`;
      return;
    }
    const env = await API.get(
      `/api/rates/subcategories?category=${encodeURIComponent(category)}`);
    if (!env.ok) {
      sub.innerHTML = `<option value="">(any load band)</option>`;
      return;
    }
    const list = (env.data && env.data.subcategories) || [];
    if (!list.length) {
      sub.innerHTML = `<option value="">(any load band)</option>`;
      // No subcategory data — still try to render preview without it
      refreshPreview();
      return;
    }
    // Always include an "any" option at top
    const items = [
      { value: "", label: "(any load band)" },
      ...list.map(s => ({
        value: s.value || "",
        label: s.label || s.value || "(unspecified)",
      })),
    ];
    setOptions(sub, items, sub.value);
    refreshPreview();
  }

  // ---- Preview ---------------------------------------------------
  function _qs(o) {
    return Object.entries(o)
      .filter(([, v]) => v !== "" && v !== null && v !== undefined)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&");
  }

  function _slabRange(s) {
    const start = s.slab_start ?? 0;
    const end = s.slab_end == null ? "∞" : s.slab_end;
    return `${start} – ${end}`;
  }

  async function refreshPreview() {
    const cat   = ($("#f_category")?.value    || "").trim();
    const sub   = ($("#f_subcategory")?.value || "").trim();
    const insp  =  $("#f_inspection")?.value  || "";
    const wrap  = $("#tariffPreviewWrap");
    const body  = $("#tariffPreviewBody");
    const sub_t = $("#tariffPreviewSubtitle");
    if (!body || !wrap) return;
    if (!cat) {
      body.innerHTML = `Pick a Category to see the active slab table.`;
      if (sub_t) sub_t.textContent = "— pick Category & Subcategory";
      // Clear readonly Condition / Load
      const ct = $("#f_condition_text");  if (ct) ct.value = "";
      const cl = $("#f_condition_load");  if (cl) cl.value = "";
      return;
    }
    body.textContent = "Loading…";
    const env = await API.get("/api/rates/preview?" + _qs({
      category:       cat,
      condition_load: sub,
      as_of_date:     insp,
    }));
    if (!env.ok) {
      body.innerHTML = `<span class="err-text">${escapeHtml(env.error || "preview failed")}</span>`;
      if (sub_t) sub_t.textContent = "— no active rate row";
      // Don't clobber #f_condition_load if user has typed it manually elsewhere
      return;
    }
    const d = env.data;
    // Update readonly "Condition / Load" text + hidden canonical key
    const ct = $("#f_condition_text");
    if (ct) ct.value = d.condition_text || "";
    const cl = $("#f_condition_load");
    if (cl) cl.value = d.condition_load || sub || "";
    // Auto-sync Supply Type from the resolved condition_load
    syncSupplyType(d.condition_load || sub);

    if (sub_t) {
      sub_t.textContent = `— schedule «${d.schedule_name || "—"}» on ${d.as_of_date}`;
    }
    const slabRows = (d.slabs || []).map(s => `
      <tr>
        <td>${escapeHtml(_slabRange(s))}</td>
        <td>${escapeHtml(s.slab_name || "")}</td>
        <td class="num">${s.rate_per_unit != null ? Number(s.rate_per_unit).toFixed(2) : "—"}</td>
      </tr>`).join("");
    const metaRows = `
      <tr><th>Schedule</th><td><code>${escapeHtml(d.schedule_name || "—")}</code></td></tr>
      <tr><th>Condition</th><td>${escapeHtml(d.condition_text || "—")}</td></tr>
      <tr><th>Fixed Charge / kW / month</th><td class="num">${d.fixed_charge != null ? `₹ ${Number(d.fixed_charge).toFixed(2)}` : "—"}</td></tr>
      <tr><th>Electricity Duty %</th><td class="num">${d.duty_percent != null ? `${Number(d.duty_percent).toFixed(2)} %` : "—"}</td></tr>
      <tr><th>Meter Rent / month</th><td class="num">${d.meter_rent != null ? `₹ ${Number(d.meter_rent).toFixed(2)}` : "—"}</td></tr>
      <tr><th>Rebate / month</th><td class="num">${d.rebate != null ? `₹ ${Number(d.rebate).toFixed(2)}` : "—"}</td></tr>
      <tr><th>Active rate-row id</th><td class="num">${d.matched_rate_row_id ?? "—"}</td></tr>`;

    body.innerHTML = `
      <div class="tariff-preview-grid">
        <div>
          <h4 class="tp-h">Slab Table</h4>
          <table class="data-table">
            <thead><tr><th>Slab (kWh)</th><th>Slab Name</th><th class="num">Rate ₹/unit</th></tr></thead>
            <tbody>${slabRows || `<tr><td colspan="3" class="small center">No slabs.</td></tr>`}</tbody>
          </table>
        </div>
        <div>
          <h4 class="tp-h">Charges &amp; Metadata</h4>
          <table class="data-table"><tbody>${metaRows}</tbody></table>
          <p class="small explanation">
            <b>How calculation uses this:</b> energy charges = slab_rate × slab_units
            summed across slabs, then × multiplier. Fixed charge =
            ${d.fixed_charge != null ? Number(d.fixed_charge).toFixed(2) : "—"}
            × Connected Load × months × multiplier. Electricity Duty is
            applied to the energy <em>subtotal</em> (pre-multiplier).
            Meter rent + rebate scale by months only — no multiplier.
          </p>
        </div>
      </div>`;
  }

  // ---- Wire-up ---------------------------------------------------
  function init() {
    if (!$("#f_category") || !$("#f_subcategory")) return;

    // Initial load — categories + their first subcategory
    loadCategories();

    // Cascade on category change
    $("#f_category").addEventListener("change", (e) => {
      loadSubcategories(e.target.value);
    });

    // Refresh preview when subcategory or inspection date changes
    $("#f_subcategory").addEventListener("change", refreshPreview);
    const insp = $("#f_inspection");
    if (insp) insp.addEventListener("change", refreshPreview);

    // Re-fetch categories whenever the Imports tab finishes uploading a
    // schedule, so the New Case dropdowns stay in sync without a refresh.
    document.body.addEventListener("click", (e) => {
      if (e.target && e.target.dataset
          && e.target.dataset.action === "upload-tariff") {
        // Delay slightly so the upload finishes before we refetch
        setTimeout(loadCategories, 1500);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
