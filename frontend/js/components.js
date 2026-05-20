/* =====================================================================
   components.js — tiny reusable UI helpers (toast, modal, formatters)
   ===================================================================== */

const UI = (function () {

  // ---------------------------------------------- formatters
  const inr = new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 2,
  });
  const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

  function money(v) {
    if (v == null || v === "" || isNaN(Number(v))) return "—";
    return inr.format(Number(v));
  }
  function number(v) {
    if (v == null || v === "" || isNaN(Number(v))) return "—";
    return num.format(Number(v));
  }
  function date(d) {
    if (!d) return "—";
    if (typeof d === "string" && d.length >= 10) return d.slice(0, 10);
    return d;
  }
  function dateTime(d) {
    if (!d) return "—";
    return String(d).replace("T", " ").slice(0, 19);
  }
  function escape(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ---------------------------------------------- toast
  const ICONS = {
    success: "✔",
    error:   "✕",
    warn:    "⚠",
    info:    "ℹ",
  };

  function toast(message, kind = "info", durationMs = 3500) {
    const root = document.getElementById("toast-container");
    if (!root) return;
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = `
      <span class="font-bold text-base leading-none">${ICONS[kind] || "ℹ"}</span>
      <span class="flex-1">${escape(message)}</span>
      <button class="opacity-70 hover:opacity-100 text-lg leading-none">×</button>
    `;
    el.querySelector("button").addEventListener("click", () => dismiss(el));
    root.appendChild(el);
    setTimeout(() => dismiss(el), durationMs);
  }
  function dismiss(el) {
    if (!el || !el.parentNode) return;
    el.classList.add("fadeout");
    setTimeout(() => el.remove(), 320);
  }

  // ---------------------------------------------- modal
  function modal({ title, html, footer, onClose }) {
    const root = document.getElementById("modal-root");
    root.innerHTML = `
      <div class="modal-overlay" data-modal-overlay>
        <div class="modal-card">
          <div class="flex items-center justify-between px-5 py-3 border-b border-slate-200">
            <h3 class="font-semibold text-slate-800">${escape(title || "")}</h3>
            <button data-modal-close class="text-slate-400 hover:text-slate-600 text-2xl leading-none">×</button>
          </div>
          <div class="p-5">${html || ""}</div>
          ${footer ? `<div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">${footer}</div>` : ""}
        </div>
      </div>`;
    function close() {
      root.innerHTML = "";
      if (onClose) onClose();
    }
    root.querySelector("[data-modal-close]").addEventListener("click", close);
    root.querySelector("[data-modal-overlay]").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) close();
    });
    return { close, root };
  }

  function confirm(message, { okText = "OK", cancelText = "Cancel", danger = false } = {}) {
    return new Promise((resolve) => {
      const m = modal({
        title: "Confirm",
        html: `<p class="text-slate-700">${escape(message)}</p>`,
        footer: `
          <button class="btn btn-secondary" data-cancel>${escape(cancelText)}</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-ok>${escape(okText)}</button>`,
      });
      m.root.querySelector("[data-cancel]").addEventListener("click", () => { m.close(); resolve(false); });
      m.root.querySelector("[data-ok]").addEventListener("click",     () => { m.close(); resolve(true);  });
    });
  }

  // ---------------------------------------------- status badge
  function statusBadge(status) {
    const map = {
      paid: "status-paid", partial: "status-partial",
      pending: "status-pending", overdue: "status-overdue",
      noticed: "status-noticed", section3_sent: "status-noticed",
      section5_sent: "status-noticed",
      open: "status-open", closed: "status-closed",
      revised: "status-revised", appealed: "status-revised",
    };
    const cls = map[status] || "status-open";
    return `<span class="px-2 py-1 rounded-full text-xs font-medium ${cls}">${escape(status || "—")}</span>`;
  }

  // ---------------------------------------------- spinner / empty
  function spinner(label = "Loading…") {
    return `
      <div class="flex flex-col items-center justify-center py-12 text-slate-400">
        <svg class="w-8 h-8 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581"/>
        </svg>
        <p class="mt-3 text-sm">${escape(label)}</p>
      </div>`;
  }
  function empty(label = "No records found.") {
    return `<div class="text-center py-12 text-slate-400"><p class="text-sm">${escape(label)}</p></div>`;
  }
  function errorBox(err) {
    const msg = err && err.message ? err.message : String(err);
    return `<div class="bg-red-50 border border-red-200 text-red-800 rounded p-4 text-sm">
              <strong>Error:</strong> ${escape(msg)}
            </div>`;
  }

  // ---------------------------------------------- helpers
  function debounce(fn, ms = 300) {
    let t; return function (...args) {
      clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  return { money, number, date, dateTime, escape,
           toast, modal, confirm, statusBadge,
           spinner, empty, errorBox, debounce };
})();
