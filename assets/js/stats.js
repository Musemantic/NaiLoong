(function () {
  "use strict";

  // 不蒜子开源版的公开接口，身份由服务端签发；每次 POST 同时累计 PV 并按身份去重 UV。
  const API = "https://bsz.iirose.cn/api";
  const COOKIE_NAME = "nai-visitor-id";
  let started = false;

  function readIdentity() {
    try {
      const cookie = document.cookie.split(";").map((part) => part.trim())
        .find((part) => part.startsWith(COOKIE_NAME + "="));
      return cookie ? decodeURIComponent(cookie.slice(COOKIE_NAME.length + 1)) : "";
    } catch (err) {
      return "";
    }
  }

  function saveIdentity(identity) {
    if (!identity) return;
    try {
      const path = new URL(".", location.href).pathname;
      document.cookie = COOKIE_NAME + "=" + encodeURIComponent(identity) +
        "; Path=" + path + "; Max-Age=31536000; SameSite=Lax" +
        (location.protocol === "https:" ? "; Secure" : "");
    } catch (err) {}
  }

  async function recordVisit() {
    if (started || document.documentElement.classList.contains("home-intro-active")) return;
    if (!/^https?:$/.test(location.protocol)) return;
    const visitors = document.getElementById("statVisitors");
    const views = document.getElementById("statViews");
    if (!visitors || !views) return;
    started = true;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const headers = { "x-bsz-referer": new URL(".", location.href).href };
      const identity = readIdentity();
      if (identity) headers.Authorization = "Bearer " + identity;
      const response = await fetch(API, {
        method: "POST", headers, signal: controller.signal, credentials: "omit", cache: "no-store"
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      saveIdentity(response.headers.get("Set-Bsz-Identity"));
      const result = await response.json();
      if (!result || result.success !== true || !result.data ||
          !Number.isSafeInteger(result.data.site_uv) || result.data.site_uv < 0 ||
          !Number.isSafeInteger(result.data.site_pv) || result.data.site_pv < 0) {
        throw new Error("Invalid visitor statistics");
      }
      visitors.textContent = result.data.site_uv.toLocaleString("zh-CN");
      views.textContent = result.data.site_pv.toLocaleString("zh-CN");
      document.dispatchEvent(new CustomEvent("visitor-stats-loaded", {
        detail: { visitors: result.data.site_uv, views: result.data.site_pv }
      }));
    } catch (err) {
      // 请求可能已被服务端计数，不自动重试；保留访客身份，避免重复累计浏览量。
      [visitors, views].forEach((node) => {
        node.textContent = "—";
        node.title = "访问统计暂时不可用";
      });
    } finally {
      clearTimeout(timer);
    }
  }

  function setupStats() {
    document.addEventListener("home-intro-finished", recordVisit, { once: true });
    recordVisit();
  }

  document.addEventListener("DOMContentLoaded", setupStats);
})();
