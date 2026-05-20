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
      const r = await API.listDevices();
      cache.devices = r.data || [];
    }
    return cache.devices;
  }
  async function getDeviceCategories() {
    if (!cache.deviceCategories) {
      const r = await API.deviceCategories();
      cache.deviceCategories = r.data || [];
    }
    return cache.deviceCategories;
  }
  async function getRateCategories() {
    if (!cache.rateCategories) {
      const r = await API.rateCategories();
      cache.rateCategories = r.data || [];
    }
    return cache.rateCategories;
  }
  async function getSystemConfig() {
    if (!cache.systemConfig) {
      const r = await API.systemConfig();
      cache.systemConfig = r.data || {};
    }
    return cache.systemConfig;
  }
  async function getHealth(force = false) {
    if (!cache.health || force) {
      try {
        const r = await API.health();
        cache.health = r.data || {};
      } catch (e) {
        cache.health = { status: "down", error: e.message };
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
