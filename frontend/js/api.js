/* =====================================================================
   api.js — single API client wrapping the backend envelope format
   The backend always returns:  { ok: bool, data?: any, error?: str, ... }
   ===================================================================== */

const API = (function () {

  // Same-origin if served by Flask; auto-detect base URL
  // Priority: 1) window.RAID_API_URL  2) same origin  3) localhost:5000
  const BASE = (function() {
    if (window.RAID_API_URL) return window.RAID_API_URL.replace(/\/$/, "");
    // If we're served from Flask (/app/index.html), the origin IS the API server
    if (window.location.origin && window.location.origin !== "null") {
      return window.location.origin;
    }
    // Fallback for file:// protocol (shouldn't happen but just in case)
    return "http://127.0.0.1:5000";
  })();

  /** Generic request helper */
  async function request(path, opts = {}) {
    const url = BASE + (path.startsWith("/") ? path : "/" + path);

    const init = {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    };
    if (opts.body !== undefined) {
      init.body = typeof opts.body === "string"
        ? opts.body
        : JSON.stringify(opts.body);
    }

    let resp;
    try {
      resp = await fetch(url, init);
    } catch (e) {
      throw new ApiError(`Network error: ${e.message}`, 0, null);
    }

    let payload = null;
    try { payload = await resp.json(); }
    catch (_) { /* non-JSON response — leave null */ }

    if (!resp.ok || !payload || payload.ok === false) {
      const msg = (payload && payload.error)
        || `HTTP ${resp.status} ${resp.statusText}`;
      const code = (payload && payload.code) || `HTTP_${resp.status}`;
      throw new ApiError(msg, resp.status, payload, code);
    }
    return payload; // { ok: true, data: ..., meta?: ... }
  }

  class ApiError extends Error {
    constructor(message, status, payload, code) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.payload = payload;
      this.code = code;
    }
  }

  // ====================== Helpers =================================
  const qs = (params) => {
    if (!params) return "";
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") p.append(k, v);
    });
    const s = p.toString();
    return s ? "?" + s : "";
  };

  // ====================== Endpoints ===============================
  return {
    ApiError,
    request,

    // ---------- system ----------
    health:        () => request("/api/health"),
    systemConfig:  () => request("/api/system/config"),

    // ---------- master data ----------
    masterFiles:        () => request("/api/master_files"),
    importAllMaster:    () => request("/api/import_all_master_data", { method: "POST" }),
    importOneMaster:    (kind, body = {}) =>
      request(`/api/import_master/${kind}`, { method: "POST", body }),

    // ---------- consumers ----------
    searchConsumers: (params) => request(`/api/consumers/search${qs(params)}`),
    getConsumer:     (account) => request(`/api/consumers/${encodeURIComponent(account)}`),
    consumerOffenseCheck: (account, params) =>
      request(`/api/consumers/${encodeURIComponent(account)}/offense-check${qs(params)}`),

    // ---------- devices + rates ----------
    listDevices:      (category) => request(`/api/devices${qs({ category })}`),
    deviceCategories: () => request("/api/devices/categories"),
    listRates:        (category) => request(`/api/rates${qs({ category })}`),
    rateCategories:   () => request("/api/rates/categories"),

    // ---------- cases ----------
    saveCase:    (body) => request("/api/cases", { method: "POST", body }),
    getCase:     (caseId) => request(`/api/cases/${encodeURIComponent(caseId)}`),
    listCases:   (params) => request(`/api/cases${qs(params)}`),
    searchCases: (params) => request(`/api/cases/search${qs(params)}`),
    calculate:   (body) => request("/api/calculate", { method: "POST", body }),
    compounding: (body) => request("/api/compounding", { method: "POST", body }),
    caseCalculate: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/calculate`,
              { method: "POST", body: body || {} }),
    caseCompounding: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/compounding`,
              { method: "POST", body: body || {} }),
    caseOffenseCheck: (caseId) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/offense-check`),
    reviseCase: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/revise`,
              { method: "POST", body }),

    // ---------- documents ----------
    documentKinds: () => request("/api/document/kinds"),
    generateDocument: (caseId, kind, body = {}) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/document/${kind}`,
              { method: "POST", body }),
    documentDownloadUrl: (docId) => `/api/documents/${docId}`,
    migrateLegacyTemplate: (file) =>
      request("/api/templates/migrate-legacy", { method: "POST", body: { file } }),

    // ---------- payments ----------
    listPayments: (caseId) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/payments`),
    recordPayment: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/payments`,
              { method: "POST", body }),
    deletePayment: (paymentId) =>
      request(`/api/payments/${paymentId}`, { method: "DELETE" }),
    recentPayments: (limit = 50) => request(`/api/payments/recent${qs({ limit })}`),

    // ---------- inquiries ----------
    listInquiries: (caseId) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/inquiries`),
    addInquiry: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/inquiries`,
              { method: "POST", body }),
    recentInquiries: (limit = 50) => request(`/api/inquiries/recent${qs({ limit })}`),
    inquiriesByMobile: (mobile) =>
      request(`/api/inquiries/by-mobile/${encodeURIComponent(mobile)}`),

    // ---------- notices ----------
    listNotices: (caseId) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/notices`),
    addNotice: (caseId, body) =>
      request(`/api/cases/${encodeURIComponent(caseId)}/notices`,
              { method: "POST", body }),
    updateNotice: (noticeId, body) =>
      request(`/api/notices/${noticeId}`, { method: "PATCH", body }),
    overdueNotices: () => request("/api/notices/overdue"),

    // ---------- dashboard ----------
    dashboardSummary:    () => request("/api/dashboard/summary"),
    timelineAlerts:      () => request("/api/dashboard/timeline-alerts"),
  };
})();
