const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const context = { window: {} };
vm.runInNewContext(fs.readFileSync("assets/js/ghimg.js", "utf8"), context);
const toRaw = context.window.GhImg.toRaw;
const toCdn = context.window.GhImg.toCdn;
const sourceDetails = context.window.GhImg.sourceDetails;
const commit = "a".repeat(40);

assert.strictEqual(
  toRaw("https://github.com/contributor/NaiLoong/blob/image/assets/memes/meme.png"),
  "https://raw.githubusercontent.com/contributor/NaiLoong/image/assets/memes/meme.png"
);
assert.strictEqual(
  toRaw("https://github.com/contributor/NaiLoong/raw/image/assets/memes/meme.png"),
  "https://raw.githubusercontent.com/contributor/NaiLoong/image/assets/memes/meme.png"
);
assert.strictEqual(
  toRaw("https://github.com/contributor/NaiLoong/raw/refs/heads/image/assets/memes/meme.png"),
  "https://raw.githubusercontent.com/contributor/NaiLoong/refs/heads/image/assets/memes/meme.png"
);
assert.strictEqual(
  toRaw("https://raw.githubusercontent.com/contributor/NaiLoong/image/assets/memes/meme.png"),
  "https://raw.githubusercontent.com/contributor/NaiLoong/image/assets/memes/meme.png"
);
assert.strictEqual(
  toRaw(`https://github.com/contributor/NaiLoong/blob/${commit}/assets/memes/meme.png`),
  `https://raw.githubusercontent.com/contributor/NaiLoong/${commit}/assets/memes/meme.png`
);
assert.strictEqual(
  toRaw(`contributor/${commit}/assets/memes/meme.png`),
  `https://raw.githubusercontent.com/contributor/NaiLoong/${commit}/assets/memes/meme.png`
);
assert.strictEqual(
  toCdn(`contributor/${commit}/assets/memes/meme.png`),
  `https://cdn.jsdelivr.net/gh/contributor/NaiLoong@${commit}/assets/memes/meme.png`
);
assert.strictEqual(
  toCdn(`https://raw.githubusercontent.com/Musemantic/NaiLoong/${commit}/assets/memes/meme%20one.png`),
  `https://cdn.jsdelivr.net/gh/musemantic/NaiLoong@${commit}/assets/memes/meme%20one.png`
);
assert.strictEqual(
  toCdn(`https://cdn.jsdelivr.net/gh/Musemantic/NaiLoong@${commit}/assets/memes/meme.png`),
  `https://cdn.jsdelivr.net/gh/musemantic/NaiLoong@${commit}/assets/memes/meme.png`
);
const compactSource = sourceDetails(`Musemantic/${commit}/assets/memes/meme.png`);
assert.strictEqual(compactSource.owner, "Musemantic");
assert.strictEqual(compactSource.profileUrl, "https://github.com/Musemantic");
assert.strictEqual(
  compactSource.url,
  `https://github.com/Musemantic/NaiLoong/blob/${commit}/assets/memes/meme.png`
);
const rawSource = sourceDetails(
  `https://raw.githubusercontent.com/Musemantic/NaiLoong/${commit}/assets/memes/meme%20one.png`
);
assert.strictEqual(rawSource.owner, "Musemantic");
assert.strictEqual(
  rawSource.url,
  `https://github.com/Musemantic/NaiLoong/blob/${commit}/assets/memes/meme%20one.png`
);
assert.strictEqual(
  context.window.GhImg.preview(
    `contributor/${commit}/assets/memes/meme.gif`,
    "naiwa",
    "animated"
  ),
  `https://cdn.jsdelivr.net/gh/lin-alg/NaiLoong@preview/previews/naiwa/animated/contributor/${commit}/assets/memes/meme.gif.webp`
);
assert.strictEqual(
  context.window.GhImg.preview(
    "assets/placeholders/fallback.gif",
    "naiwa",
    "animated"
  ),
  null
);

const ghimg = context.window.GhImg;
const mixed = `MixedOwner/${commit.toUpperCase()}/assets/memes/Laugh.png`;
assert.strictEqual(
  ghimg.asset("assets/pet/naifrog-sheet.webp"),
  "https://cdn.jsdelivr.net/gh/lin-alg/NaiLoong@main/assets/pet/naifrog-sheet.webp"
);
assert.strictEqual(
  ghimg.candidates(mixed, "direct")[0],
  `https://gh-proxy.com/https://raw.githubusercontent.com/mixedowner/NaiLoong/${commit}/assets/memes/Laugh.png`
);
const candidateUrls = ghimg.candidates(mixed, "direct");
assert(candidateUrls.some((url) => url.startsWith("https://cdn.jsdelivr.net/")), "jsDelivr should remain available as a fallback");
assert(candidateUrls.indexOf(candidateUrls.find((url) => url.startsWith("https://cdn.jsdelivr.net/"))) < candidateUrls.length - 1, "jsDelivr must be tried before raw");
assert.strictEqual(candidateUrls[candidateUrls.length - 1], ghimg.toRaw(mixed), "raw must be the final fallback");
assert.strictEqual(
  ghimg.preview(mixed, "naiwa", "static"),
  ghimg.preview(`https://github.com/MixedOwner/NaiLoong/blob/${commit}/assets/memes/Laugh.png`, "naiwa", "static")
);
assert.strictEqual(
  ghimg.preview(mixed, "naiwa", "static"),
  `https://cdn.jsdelivr.net/gh/lin-alg/NaiLoong@preview/previews/naiwa/static/mixedowner/${commit}/assets/memes/Laugh.png.webp`
);
assert.notStrictEqual(
  ghimg.preview(mixed, "naiwa", "static"),
  ghimg.preview(mixed.replace(".png", ".gif"), "naiwa", "static")
);
assert.strictEqual(
  ghimg.preview(`contributor/${commit}/meme%20one%2Epng`, "naiwa", "static"),
  `https://cdn.jsdelivr.net/gh/lin-alg/NaiLoong@preview/previews/naiwa/static/contributor/${commit}/meme%20one.png.webp`
);
assert.strictEqual(
  toRaw(`https://github.com/MixedOwner/NaiLoong/blob/FeatureBranch/Laugh.png`),
  "https://raw.githubusercontent.com/mixedowner/NaiLoong/FeatureBranch/Laugh.png"
);

ghimg.configure({ proxies: [] });
const originalPreview = ghimg.preview(mixed, "naiwa", "static");
const legacyPreview = ghimg.previewLegacy(mixed, "naiwa", "static");
assert(legacyPreview.includes(`/MixedOwner/${commit}/assets/memes/Laugh.webp`));
assert(
  ghimg.previewLegacy(`https://github.com/MixedOwner/NaiLoong/blob/${commit}/assets/memes/Laugh.png`, "naiwa", "static")
    .includes(`/mixedowner/${commit}/assets/memes/Laugh.webp`)
);
const image = {
  tagName: "IMG",
  getAttribute: (name) => ({
    src: originalPreview,
    "data-preview-legacy": legacyPreview,
    "data-original-url": ghimg.link(mixed)
  })[name] || null
};
ghimg.decorate(image);
assert.strictEqual(image._gh.list[0], originalPreview);
assert.strictEqual(ghimg.advance(image), legacyPreview);
assert(image._gh.list.includes(ghimg.link(mixed)), "preview failures should fall back to the original image URL");

console.log("GitHub image URL conversion passed");
