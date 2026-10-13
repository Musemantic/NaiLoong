const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("assets/js/app.js", "utf8").replace(
  'document.addEventListener("DOMContentLoaded", init);',
  "window.resources = { fetchJSON };"
);

function setup(fetch) {
  const timers = new Set();
  const context = {
    window: {}, fetch, AbortController,
    setTimeout(callback, delay) {
      const timer = setTimeout(callback, delay === 10000 ? delay : 0);
      timers.add(timer);
      return timer;
    },
    clearTimeout(timer) { timers.delete(timer); clearTimeout(timer); }
  };
  vm.runInNewContext(source, context);
  return { fetchJSON: context.window.resources.fetchJSON, timers };
}

(async () => {
  let requests = 0;
  const recovered = setup(async () => {
    requests += 1;
    if (requests === 1) throw new TypeError("Failed to fetch");
    return { ok: true, json: async () => ({ ready: true }) };
  });
  assert.strictEqual((await recovered.fetchJSON("retry.json")).ready, true);
  assert.strictEqual(requests, 2, "a transient network failure should recover");
  await recovered.fetchJSON("retry.json");
  assert.strictEqual(requests, 2, "successfully loaded JSON should be reused");

  for (const failure of ["network", "http", "json", "timeout"]) {
    let attempts = 0;
    const broken = setup(async () => {
      attempts += 1;
      if (failure === "network") throw new TypeError("Failed to fetch");
      if (failure === "timeout") throw Object.assign(new Error("Aborted"), { name: "AbortError" });
      return {
        ok: failure !== "http", status: 404,
        json: async () => { throw new SyntaxError("Invalid JSON"); }
      };
    });
    await assert.rejects(broken.fetchJSON(`${failure}.json`));
    assert.strictEqual(attempts, failure === "network" ? 3 : 1, "retries must be bounded and limited to temporary network failures");
  }
  console.log("resource loading recovery passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
