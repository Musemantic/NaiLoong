const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

// 运行页面实际使用的物理函数；不启动 DOM、音频或网络请求。
const source = fs.readFileSync("assets/js/app.js", "utf8").replace(
  'document.addEventListener("DOMContentLoaded", init);',
  "window.intro = { precomputeIntro, simulateIntro };"
);
let seed = 1;
const math = Object.create(Math);
math.random = () => {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
};
const context = { window: {}, Math: math };
vm.runInNewContext(source, context);
const { precomputeIntro, simulateIntro } = context.window.intro;

function corners(body, size) {
  const angle = body.rotation * Math.PI / 180;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) => ({
    x: body.x + size / 2 * (x * c - y * s),
    y: body.y + size / 2 * (x * s + y * c)
  }));
}

function overlap(a, b) {
  let minimum = Infinity;
  for (const polygon of [a, b]) {
    for (let i = 0; i < 4; i++) {
      const next = polygon[(i + 1) % 4];
      const dx = next.x - polygon[i].x;
      const dy = next.y - polygon[i].y;
      const length = Math.hypot(dx, dy);
      const project = (p) => (p.x * -dy + p.y * dx) / length;
      const pa = a.map(project);
      const pb = b.map(project);
      const depth = Math.min(Math.max(...pa), Math.max(...pb)) - Math.max(Math.min(...pa), Math.min(...pb));
      if (depth <= 0) return 0;
      minimum = Math.min(minimum, depth);
    }
  }
  return minimum;
}

const viewports = [[320, 568], [390, 844], [436, 956], [768, 1024], [1024, 768], [1920, 1080], [2560, 1440], [3840, 2160], [5120, 2160], [7680, 4320]];
for (const [width, height] of viewports) {
  const rootFont = width >= 1600 ? Math.min(24, width * 0.01) : 16;
  const size = width <= 767 ? Math.max(72, Math.min(96, width * 0.2)) : Math.max(6 * rootFont, Math.min(9 * rootFont, width * 0.12));
  const tiles = Array.from({ length: 4 }, () => ({ offsetWidth: size, style: {} }));
  context.window.innerWidth = width;
  context.window.innerHeight = height;
  let longest = 0;
  for (let run = 0; run < 30; run++) {
    seed = run + 1;
    const route = precomputeIntro(tiles);
    const label = `${width}×${height}, seed ${run + 1}`;
    assert(route && route.complete, `all cards must leave: ${label}`);
    assert(route.events.some((event) => !event.edge), `card collisions must occur: ${label}`);
    assert.strictEqual(route.frames[20].cues.length, 4, `four simultaneous cues: ${label}`);
    route.frames[28].bodies.forEach((body, i) => {
      assert.strictEqual(body.x, route.frames[0].bodies[i].x, `no early launch: ${label}`);
      assert.strictEqual(body.y, route.frames[0].bodies[i].y, `no early launch: ${label}`);
      const next = route.frames[29].bodies[i];
      assert(Math.hypot(next.x - body.x, next.y - body.y) > 0, `all four launch together: ${label}`);
    });
    for (const [frameIndex, frame] of route.frames.entries()) {
      const visible = frame.bodies.filter((body) => !body.done).map((body) => corners(body, size)).filter((polygon) =>
        Math.max(...polygon.map((p) => p.x)) > 0 && Math.min(...polygon.map((p) => p.x)) < width &&
        Math.max(...polygon.map((p) => p.y)) > 0 && Math.min(...polygon.map((p) => p.y)) < height
      );
      for (let i = 0; i < visible.length; i++) {
        for (let j = i + 1; j < visible.length; j++) {
          const depth = overlap(visible[i], visible[j]);
          assert(depth < 0.1, `cards must not penetrate: ${label}, frame ${frameIndex}, overlap ${depth}, bodies ${JSON.stringify(frame.bodies)}`);
        }
      }
    }
    longest = Math.max(longest, route.frames.length / 60);
  }
  console.log(`${width}×${height}: 30 complete routes with collisions, no overlap, max ${longest.toFixed(2)}s`);
}

// 无碰撞的直线运动也必须明显减速，不能只在撞边时损失速度。
const rolling = simulateIntro([{
  x: 300, y: 600, vx: 1200, vy: 0, launchVx: 1200, launchVy: 0,
  size: 80, rotation: 0, spin: 0, launchFrame: 0, entered: true
}], 2000, 1200, [20], [1], 700);
const distance = (frame) => rolling.frames[frame + 1].bodies[0].x - rolling.frames[frame].bodies[0].x;
assert(distance(30) < distance(0) * 0.8, "rolling friction should visibly reduce speed before any impact");
assert.strictEqual(rolling.events.length, 0, "friction test must not include wall collisions");
console.log("intro physics passed");
