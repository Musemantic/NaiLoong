const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("assets/js/app.js", "utf8").replace(
  'document.addEventListener("DOMContentLoaded", init);',
  "window.voiceMetaFor = voiceMetaFor;"
);
const context = { window: {} };
vm.runInNewContext(source, context);
const voiceMetaFor = context.window.voiceMetaFor;

const frog = { id: "naiwa", voice: "naiwa/voice.json" };
const egg = { id: "naidan", voice: "naidan/voice.json" };
const emblem = { id: "nai-emblem" };
const others = { id: "others" };
const custom = { id: "custom", voice: "custom/voice.json" };
const manifest = [frog, egg, emblem, others, custom];

assert.strictEqual(voiceMetaFor(emblem, manifest), frog, "unconfigured roles inherit frog voices");
assert.strictEqual(voiceMetaFor(others, manifest), frog, "other unconfigured roles inherit frog voices");
assert.strictEqual(voiceMetaFor(egg, manifest), egg, "the egg role keeps its own voice configuration");
assert.strictEqual(voiceMetaFor(custom, manifest), custom, "explicit role voices take precedence");
assert.strictEqual(voiceMetaFor(null, manifest), null, "missing role metadata stays missing");
console.log("voice defaults passed");
