/* =====================================================================
   state.js — small in-memory state + cache + tiny event bus
   ===================================================================== */

const State = (function () {
  const cache = {
    devices:        null,   // [{id, device_name, category, ...}]
    deviceCategories: null,
    rateCategories: null,
    systemConfig:   null,
    health:         null,
  };

  const listeners = {};
  function on(event, fn)   { (listeners[event] ||= []).push(fn); }
  function off(event, fn)  { listeners[event] = (listeners[event]||[]).filter(f => f !== fn); }
  function emit(event, p)  { (listeners[event] || []).forEach(fn => { try { fn(p); } catch (e) { console.error(e); } }); }

  // ---- cached fetchers (memoised first call) ----
  async function getDevices() {
    if (!cache.devices) {
      try {
        const r = await API.listDevices();
        cache.devices = r.data || [];
      } catch (e) {
        console.warn("Failed to load devices:", e.message);
        cache.devices = [];
      }
    }
    return cache.devices;
  }
  async function getDeviceCategories() {
    if (!cache.deviceCategories) {
      try {
        const r = await API.deviceCategories();
        cache.deviceCategories = r.data || [];
      } catch (e) {
        console.warn("Failed to load device categories:", e.message);
        cache.deviceCategories = [];
      }
    }
    return cache.deviceCategories;
  }
  async function getRateCategories() {
    if (!cache.rateCategories) {
      try {
        const r = await API.rateCategories();
        cache.rateCategories = r.data || [];
      } catch (e) {
        console.warn("Failed to load rate categories:", e.message);
        cache.rateCategories = [];
      }
    }
    return cache.rateCategories;
  }
  async function getSystemConfig() {
    if (!cache.systemConfig) {
      try {
        const r = await API.systemConfig();
        cache.systemConfig = r.data || {};
      } catch (e) {
        console.warn("Failed to load system config:", e.message);
        cache.systemConfig = {};
      }
    }
    return cache.systemConfig;
  }
  async function getHealth(force = false) {
    if (!cache.health || force) {
      try {
        const r = await API.health();
        cache.health = r.data || {};
      } catch (e) {
        cache.health = { status: "down", error: e.message, db_ok: false };
      }
    }
    return cache.health;
  }

  function invalidate(key) {
    if (key) cache[key] = null;
    else Object.keys(cache).forEach(k => cache[k] = null);
  }

  return { cache, on, off, emit, invalidate,
           getDevices, getDeviceCategories, getRateCategories,
           getSystemConfig, getHealth };
})();
