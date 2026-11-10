const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("assets/js/stats.js", "utf8");
const settle = () => new Promise((resolve) => setImmediate(resolve));

function setup({ intro = true, cookie = "", href = "https://example.com/NaiLoong/", fetch, cookieBlocked = false } = {}) {
  const listeners = new Map();
  const nodes = Object.fromEntries(["statVisitors", "statViews"].map((id) => [id, { textContent: "—" }]));
  const writes = [];
  const requests = [];
  const events = [];
  const timers = new Map();
  let timerId = 0;
  const document = {
    documentElement: { classList: { contains: () => intro } },
    getElementById: (id) => nodes[id],
    get cookie() {
      if (cookieBlocked) throw new Error("Cookies are blocked");
      return cookie;
    },
    set cookie(value) {
      if (cookieBlocked) throw new Error("Cookies are blocked");
      writes.push(value);
      cookie = value.split(";")[0];
    },
    addEventListener(type, callback, options) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push({ callback, once: options && options.once });
    },
    dispatchEvent(event) { events.push(event); }
  };
  vm.runInNewContext(source, {
    document, location: new URL(href), URL, AbortController,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return fetch(url, options);
    }
  });
  const dispatch = async (type) => {
    const handlers = listeners.get(type) || [];
    listeners.set(type, handlers.filter((handler) => !handler.once));
    handlers.forEach(({ callback }) => callback());
    await settle();
  };
  return { nodes, requests, writes, timers, events, dispatch, enter() { intro = false; } };
}

function response(data, identity = "") {
  return {
    ok: true,
    headers: { get: (name) => name === "Set-Bsz-Identity" ? identity : null },
    json: async () => ({ success: true, data })
  };
}

(async () => {
  // 模拟服务按身份去重 UV，每一次正式页面加载都增加 PV。
  let pv = 1000;
  const identities = new Set();
  const api = async (url, { method, headers }) => {
    assert.strictEqual(url, "https://bsz.iirose.cn/api");
    assert.strictEqual(method, "POST");
    assert.strictEqual(headers["x-bsz-referer"], "https://example.com/NaiLoong/");
    const identity = headers.Authorization ? headers.Authorization.slice(7) : "signed-visitor-id";
    identities.add(identity);
    return response({ site_uv: identities.size, site_pv: ++pv }, headers.Authorization ? "" : identity);
  };
  const first = setup({ fetch: api });
  await first.dispatch("DOMContentLoaded");
  assert.strictEqual(first.requests.length, 0, "waiting at the intro must not count a visit");
  assert.strictEqual(first.writes.length, 0, "waiting at the intro must not create an identity cookie");
  first.enter();
  await first.dispatch("home-intro-finished");
  assert.strictEqual(first.requests.length, 1);
  assert.strictEqual(first.nodes.statVisitors.textContent, "1");
  assert.strictEqual(first.nodes.statViews.textContent, "1,001");
  assert.strictEqual(first.events.length, 1);
  assert.strictEqual(first.events[0].type, "visitor-stats-loaded");
  assert.strictEqual(first.events[0].detail.visitors, 1);
  assert.strictEqual(first.events[0].detail.views, 1001);
  assert.match(first.writes[0], /^nai-visitor-id=signed-visitor-id; Path=\/NaiLoong\/; Max-Age=31536000; SameSite=Lax; Secure$/);
  await first.dispatch("home-intro-finished");
  await first.dispatch("hashchange");
  await first.dispatch("DOMContentLoaded");
  assert.strictEqual(first.requests.length, 1, "repeated events and in-page navigation must not recount");
  assert.strictEqual(first.timers.size, 0);

  const reload = setup({ intro: false, fetch: api, cookie: "other=value; nai-visitor-id=signed-visitor-id", href: "https://example.com/NaiLoong/index.html?query=test#/naiwa" });
  await reload.dispatch("DOMContentLoaded");
  assert.strictEqual(reload.requests[0].options.headers.Authorization, "Bearer signed-visitor-id");
  assert.strictEqual(reload.nodes.statVisitors.textContent, "1", "a returning visitor keeps the same UV");
  assert.strictEqual(reload.nodes.statViews.textContent, "1,002", "a reload adds one PV");
  assert.strictEqual(reload.writes.length, 0, "an empty response identity must not erase the cookie");

  for (const kind of ["http", "network", "invalid", "json"]) {
    const broken = setup({ intro: false, cookie: "nai-visitor-id=existing", fetch: async () => {
      if (kind === "network") throw new TypeError("Failed to fetch");
      if (kind === "http") return { ok: false, status: 503 };
      if (kind === "json") return { ...response({}), json: async () => { throw new SyntaxError("Invalid JSON"); } };
      return response({ site_uv: -1, site_pv: "100" });
    } });
    await broken.dispatch("DOMContentLoaded");
    await broken.dispatch("home-intro-finished");
    assert.strictEqual(broken.requests.length, 1, "a failed counting request must not be retried automatically");
    assert.strictEqual(broken.nodes.statVisitors.textContent, "—");
    assert.strictEqual(broken.nodes.statViews.textContent, "—");
    assert.strictEqual(broken.nodes.statViews.title, "访问统计暂时不可用");
    assert.strictEqual(broken.writes.length, 0, "failure must preserve the existing visitor identity");
    assert.strictEqual(broken.timers.size, 0);
  }

  const timedOut = setup({ intro: false, fetch: (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("Aborted")));
  }) });
  await timedOut.dispatch("DOMContentLoaded");
  Array.from(timedOut.timers.values()).forEach((callback) => callback());
  await settle();
  assert.strictEqual(timedOut.nodes.statViews.title, "访问统计暂时不可用");
  assert.strictEqual(timedOut.requests.length, 1);
  assert.strictEqual(timedOut.timers.size, 0);

  const blocked = setup({ intro: false, cookieBlocked: true, fetch: api });
  await blocked.dispatch("DOMContentLoaded");
  assert.strictEqual(blocked.nodes.statViews.textContent, "1,003", "blocked cookies must not break the page or counter response");

  const local = setup({ intro: false, href: "http://localhost:8080/NaiLoong/", fetch: async () => response({ site_uv: 2, site_pv: 3 }, "id/with+symbols=") });
  await local.dispatch("DOMContentLoaded");
  assert.match(local.writes[0], /nai-visitor-id=id%2Fwith%2Bsymbols%3D;/);
  assert.ok(!local.writes[0].includes("; Secure"), "HTTP previews must be able to retain the cookie");

  const file = setup({ intro: false, href: "file:///NaiLoong/index.html", fetch: api });
  await file.dispatch("DOMContentLoaded");
  assert.strictEqual(file.requests.length, 0);
  console.log("visitor statistics, cookie identity, intro gating and failure handling passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
