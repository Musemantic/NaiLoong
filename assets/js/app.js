(function () {
  "use strict";

  const CONFIG = {
    repo: "https://github.com/lin-alg/NaiLoong",
    dataBase: "data/",
    tagDimensions: "data/tag-translations.json",
    fallback: "assets/placeholders/fallback.gif"
  };

  const PAGE_SIZES = [4, 8, 16, 32, 64];
  const DEFAULT_PAGE_SIZE = 8;
  const STAGGER_CAP = 14;

  const el = {};
  const state = {
    manifest: [],
    tagDimensions: {},
    chars: new Map(),
    charId: null,
    subId: null,
    query: "",
    selected: new Map(),
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE
  };
  const cache = new Map();

  const ICON_COPY =
    '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.75 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path fill="currentColor" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg>';

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[ch]);
  }

  async function fetchJSON(path) {
    if (cache.has(path)) return cache.get(path);
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(path + " → HTTP " + res.status);
    const data = await res.json();
    cache.set(path, data);
    return data;
  }

  function toast(message) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    requestAnimationFrame(() => el.toast.classList.add("is-on"));
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      el.toast.classList.remove("is-on");
      setTimeout(() => {
        el.toast.hidden = true;
      }, 200);
    }, 1800);
  }

  function applyRepoLinks() {
    document.querySelectorAll("[data-repo-link]").forEach((node) => {
      node.href = CONFIG.repo + (node.dataset.repoSuffix || "");
    });
    document.querySelectorAll("a[href]").forEach((node) => {
      let url = null;
      try {
        url = new URL(node.href, location.href);
      } catch (err) {
        return;
      }
      const external = (url.protocol === "https:" || url.protocol === "http:") && url.host !== location.host;
      if (!external) return;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    });
  }

  function charDir(meta) {
    const first = meta.subcategories && meta.subcategories[0] ? meta.subcategories[0].file : "";
    const cut = first.indexOf("/") === -1 ? "" : first.slice(0, first.indexOf("/") + 1);
    return cut;
  }

  async function loadChar(meta) {
    const subEntries = await Promise.all(
      (meta.subcategories || []).map(async (sub) => {
        const items = await fetchJSON(CONFIG.dataBase + sub.file);
        return [sub.id, { meta: sub, items: Array.isArray(items) ? items : [] }];
      })
    );

    let tagsJson = {};
    try {
      const tagsPath = meta.tags
        ? CONFIG.dataBase + meta.tags
        : CONFIG.dataBase + charDir(meta) + "tags.json";
      tagsJson = await fetchJSON(tagsPath);
    } catch (err) {
      tagsJson = {};
    }

    const tagIndex = window.MemeSearch.buildTagIndex(tagsJson, state.tagDimensions);
    const subs = new Map();
    subEntries.forEach(([subId, sub]) => {
      sub.rows = window.MemeSearch.buildList(sub.items, tagIndex);
      subs.set(subId, sub);
    });

    let total = 0;
    subs.forEach((sub) => {
      total += sub.items.length;
    });

    return { meta, subs, tagIndex, total };
  }

  function currentChar() {
    return state.charId ? state.chars.get(state.charId) : null;
  }

  function currentSub() {
    const char = currentChar();
    if (!char || !state.subId) return null;
    return char.subs.get(state.subId) || null;
  }

  function activeTokens() {
    return window.MemeSearch.tokenize(state.query);
  }

  function matchTokens(row, tokens) {
    if (!tokens.length) return true;
    return tokens.every((token) => row.hay.indexOf(token) !== -1);
  }

  function matchFacets(row) {
    if (!state.selected.size) return true;
    for (const indexes of state.selected.values()) {
      if (!indexes.size) continue;
      let hit = false;
      for (const idx of indexes) {
        if (row.tags.has(idx)) {
          hit = true;
          break;
        }
      }
      if (!hit) return false;
    }
    return true;
  }

  function filteredRows(char, sub) {
    const tokens = activeTokens();
    const withFacets = char === currentChar();
    return sub.rows.filter((row) => matchTokens(row, tokens) && (!withFacets || matchFacets(row)));
  }

  function charMatchedCount(char) {
    const tokens = activeTokens();
    const withFacets = char.meta.id === state.charId;
    let n = 0;
    char.subs.forEach((sub) => {
      sub.rows.forEach((row) => {
        if (matchTokens(row, tokens) && (!withFacets || matchFacets(row))) n += 1;
      });
    });
    return n;
  }

  function renderSidebar() {
    el.sidebarNav.innerHTML = state.manifest
      .map((meta) => {
        const data = state.chars.get(meta.id);
        const active = meta.id === state.charId ? " is-active" : "";
        const count = data ? charMatchedCount(data) : "…";
        return (
          '<a class="side-item' +
          active +
          '" href="#/' +
          esc(meta.id) +
          '" data-char="' +
          esc(meta.id) +
          '">' +
          '<span class="side-icon" aria-hidden="true">' +
          esc(meta.icon || "🍼") +
          "</span>" +
          '<span class="side-name">' +
          esc(meta.name) +
          "</span>" +
          '<span class="side-count" data-total="' +
          (data ? data.total : 0) +
          '">' +
          count +
          "</span>" +
          "</a>"
        );
      })
      .join("");
  }

  function renderTabs() {
    const char = currentChar();
    if (!char) {
      el.subTabs.innerHTML = "";
      return;
    }
    el.subTabs.innerHTML = char.meta.subcategories
      .map((sub) => {
        const data = char.subs.get(sub.id);
        const active = sub.id === state.subId ? " is-active" : "";
        const matched = data ? filteredRows(char, data).length : 0;
        return (
          '<button class="tab' +
          active +
          '" type="button" role="tab" aria-selected="' +
          (sub.id === state.subId) +
          '" data-sub="' +
          esc(sub.id) +
          '">' +
          esc(sub.name) +
          '<span class="tab-count">' +
          matched +
          "</span></button>"
        );
      })
      .join("");
  }

  function renderTagPanel() {
    const char = currentChar();
    if (!char || !char.tagIndex.cats.length) {
      el.tagPanel.innerHTML = "";
      return;
    }
    el.tagPanel.innerHTML = char.tagIndex.cats
      .map((cat) => {
        const activeSet = state.selected.get(cat.key) || new Set();
        const chips = cat.items
          .map((rec) => {
            const on = activeSet.has(rec.flat) ? " is-on" : "";
            return (
              '<button class="chip' +
              on +
              '" type="button" data-flat="' +
              rec.flat +
              '" data-cat="' +
              esc(cat.key) +
              '" aria-pressed="' +
              (on ? "true" : "false") +
              '">' +
              esc(rec.label) +
              "</button>"
            );
          })
          .join("");
        return (
          '<div class="tag-group"><span class="tag-group-label">' +
          esc(cat.label) +
          '</span><div class="chip-row">' +
          chips +
          "</div></div>"
        );
      })
      .join("");
  }

  function skeletonMarkup(count) {
    let out = "";
    for (let i = 0; i < count; i += 1) {
      out +=
        '<div class="skeleton"><div class="skeleton-media"></div>' +
        '<div class="skeleton-line"></div><div class="skeleton-line short"></div></div>';
    }
    return out;
  }

  function cardMarkup(item, charMeta, index) {
    const alt = item.title + " · " + charMeta.name;
    const src = esc(window.GhImg ? (window.GhImg.toRaw(item.url) || item.url) : item.url);
    const link = esc(window.GhImg ? window.GhImg.link(item.url) : item.url);
    const tags = window.MemeSearch.labelsOf(
      window.MemeSearch.resolveRawTags(item.tags, currentChar().tagIndex),
      currentChar().tagIndex
    )
      .map((label) => '<span class="tag">' + esc(label) + "</span>")
      .join("");

    return (
      '<article class="card" style="--i:' +
      Math.min(index, STAGGER_CAP) +
      '">' +
      '<div class="card-media"><img src="' +
      src +
      '" alt="' +
      esc(alt) +
      '" loading="lazy" decoding="async"></div>' +
      '<div class="card-body"><div class="card-head">' +
      '<h3 class="card-title">' +
      esc(item.title) +
      "</h3>" +
      '<button class="btn btn-ghost icon-btn copy-btn" type="button" title="复制图片链接" aria-label="复制图片链接" data-url="' +
      link +
      '">' +
      ICON_COPY +
      "</button></div>" +
      (tags ? '<div class="card-tags">' + tags + "</div>" : "") +
      "</div></article>"
    );
  }

  function pageNumbers(page, pageCount) {
    if (pageCount <= 7) {
      const all = [];
      for (let i = 1; i <= pageCount; i += 1) all.push(i);
      return all;
    }
    const pages = [1, pageCount];
    for (let i = Math.max(2, page - 1); i <= Math.min(pageCount - 1, page + 1); i += 1) {
      pages.push(i);
    }
    pages.sort((a, b) => a - b);
    const out = [];
    let prev = 0;
    pages.forEach((p) => {
      if (prev && p - prev > 1) out.push("…");
      out.push(p);
      prev = p;
    });
    return out;
  }

  function pagerMarkup(page, pageCount, matched, rangeStart, rangeEnd) {
    const options = PAGE_SIZES.map(
      (size) =>
        '<option value="' +
        size +
        '"' +
        (size === state.pageSize ? " selected" : "") +
        ">" +
        size +
        "</option>"
    ).join("");

    const numbers = pageNumbers(page, pageCount)
      .map((p) => {
        if (p === "…") return '<span class="pager-ellipsis" aria-hidden="true">…</span>';
        const on = p === page ? " is-on" : "";
        return (
          '<button class="pager-btn pager-num' +
          on +
          '" type="button" data-page="' +
          p +
          '" aria-label="第 ' +
          p +
          ' 页"' +
          (p === page ? ' aria-current="page"' : "") +
          ">" +
          p +
          "</button>"
        );
      })
      .join("");

    return (
      '<div class="pager-info"><strong>' +
      matched +
      "</strong> 条结果 · 第 " +
      rangeStart +
      "-" +
      rangeEnd +
      ' 条</div>' +
      '<div class="pager-nav">' +
      '<button class="pager-btn" type="button" data-page="prev"' +
      (page <= 1 ? " disabled" : "") +
      ">‹ 上一页</button>" +
      numbers +
      '<button class="pager-btn" type="button" data-page="next"' +
      (page >= pageCount ? " disabled" : "") +
      ">下一页 ›</button>" +
      "</div>" +
      '<label class="pager-size">每页 <select class="page-size-select" aria-label="每页表情数">' +
      options +
      "</select></label>"
    );
  }

  function renderPager(matched, pageCount, rangeStart, rangeEnd) {
    const markup = pagerMarkup(state.page, pageCount, matched, rangeStart, rangeEnd);
    [el.pagerBottom].forEach((node) => {
      node.innerHTML = markup;
      node.hidden = matched === 0;
    });
  }

  function renderGrid() {
    const char = currentChar();
    const sub = currentSub();

    if (!char || !sub) {
      el.grid.innerHTML = "";
      el.resultCount.textContent = "—";
      el.pagerBottom.hidden = true;
      return;
    }

    const list = filteredRows(char, sub);
    const total = list.length;
    const pageCount = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > pageCount) state.page = pageCount;
    if (state.page < 1) state.page = 1;

    const start = (state.page - 1) * state.pageSize;
    const pageItems = list.slice(start, start + state.pageSize).map((row) => row.item);
    const rangeStart = total === 0 ? 0 : start + 1;
    const rangeEnd = total === 0 ? 0 : start + pageItems.length;

    const filtering = state.query.trim() !== "" || state.selected.size > 0;
    el.clearFilters.hidden = !filtering;
    el.resultCount.textContent = "显示 " + total + " / " + sub.items.length;
    el.emptyState.hidden = total !== 0;

    el.grid.innerHTML = pageItems.map((item, i) => cardMarkup(item, char.meta, i)).join("");

    el.grid.querySelectorAll("img").forEach((img) => {
      if (window.GhImg) window.GhImg.decorate(img);
      if (img.complete && img.naturalWidth > 0) img.classList.add("is-loaded");
    });

    renderPager(total, pageCount, rangeStart, rangeEnd);
  }

  function render() {
    renderSidebar();
    renderTabs();
    renderTagPanel();
    renderGrid();
  }

  function scrollToGallery() {
    const target = $("gallery");
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function applyRoute() {
    const raw = location.hash.slice(1);
    const hasRoute = raw.startsWith("/");
    const parts = hasRoute ? raw.replace(/^\//, "").split("/").filter(Boolean) : [];

    if (!state.manifest.length) return;

    let charId = parts[0];
    if (!charId || !state.chars.has(charId)) charId = state.manifest[0].id;
    const char = state.chars.get(charId);

    let subId = parts[1];
    if (!subId || !char.subs.has(subId)) subId = char.meta.subcategories[0].id;

    const charChanged = charId !== state.charId;
    const subChanged = subId !== state.subId;
    if (charChanged) state.selected.clear();
    if (charChanged || subChanged) state.page = 1;

    state.charId = charId;
    state.subId = subId;

    if (hasRoute && raw !== "/" + charId + "/" + subId) {
      try {
        history.replaceState(null, "", "#/" + charId + "/" + subId);
      } catch (err) {
      }
    }

    render();
  }

  function resetFilters() {
    state.query = "";
    state.selected.clear();
    state.page = 1;
    el.searchInput.value = "";
    render();
  }

  function toggleChip(flat, catKey) {
    const set = state.selected.get(catKey) || new Set();
    if (set.has(flat)) set.delete(flat);
    else set.add(flat);
    if (set.size) state.selected.set(catKey, set);
    else state.selected.delete(catKey);
    state.page = 1;
    render();
  }

  function goToPage(target) {
    const sub = currentSub();
    if (!sub) return;
    const list = filteredRows(currentChar(), sub);
    const pageCount = Math.max(1, Math.ceil(list.length / state.pageSize));
    let next = state.page;
    if (target === "prev") next = state.page - 1;
    else if (target === "next") next = state.page + 1;
    else next = Number(target);
    if (!Number.isFinite(next)) return;
    next = Math.min(Math.max(next, 1), pageCount);
    if (next === state.page) return;
    state.page = next;
    renderGrid();
    scrollToGallery();
  }

  function applySearch() {
    state.query = el.searchInput.value.trim();
    state.page = 1;
    render();
    scrollToGallery();
  }

  function markBroken(img) {
    const media = img.closest(".card-media");
    if (!media) return;
    img.remove();
    media.classList.add("is-broken");
    media.innerHTML = "<span>图裂了 · broken link</span>";
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }

  function storageGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (err) {
      return;
    }
  }

  function applyTheme(mode) {
    document.documentElement.dataset.theme = mode;
    storageSet("nai-theme", mode);
    const icons = { auto: "🌗", light: "☀️", dark: "🌙" };
    const names = { auto: "主题：跟随系统", light: "主题：浅色", dark: "主题：深色" };
    el.themeIcon.textContent = icons[mode] || icons.auto;
    el.themeToggle.title = names[mode] || names.auto;
    el.themeToggle.setAttribute("aria-label", names[mode] || names.auto);
  }

  function cycleTheme() {
    const order = ["auto", "dark", "light"];
    const next = order[(order.indexOf(document.documentElement.dataset.theme) + 1) % order.length];
    applyTheme(next);
    toast("已切换主题：" + ({ auto: "跟随系统", dark: "深色", light: "浅色" })[next]);
  }

  function prefersReducedMotion() {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function countUp(node, target, delay) {
    if (!node) return;
    const value = Number(target) || 0;
    if (prefersReducedMotion()) {
      node.textContent = value;
      return;
    }
    const duration = 1200;
    const start = performance.now() + (delay || 0);
    node.textContent = "0";
    const step = (now) => {
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = Math.round(value * eased);
      if (t < 1) requestAnimationFrame(step);
      else node.textContent = value;
    };
    requestAnimationFrame(step);
  }

  function renderStats() {
    let items = 0;
    let tags = 0;
    state.chars.forEach((char) => {
      items += char.total;
      tags += char.tagIndex.size;
    });
    countUp($("statItems"), items, 0);
    countUp($("statChars"), state.manifest.length, 120);
    countUp($("statTags"), tags, 240);
  }

  function setupReveal() {
    const nodes = document.querySelectorAll(".reveal");
    if (!nodes.length) return;
    if (typeof IntersectionObserver !== "function") {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    nodes.forEach((node, i) => {
      node.style.setProperty("--d", (i % 5) * 70 + "ms");
      observer.observe(node);
    });
  }

  function bindEvents() {
    window.addEventListener("hashchange", applyRoute);

    el.subTabs.addEventListener("click", (event) => {
      const btn = event.target.closest(".tab");
      if (!btn) return;
      location.hash = "#/" + state.charId + "/" + btn.dataset.sub;
    });

    el.sidebarNav.addEventListener("click", (event) => {
      const link = event.target.closest(".side-item");
      if (!link) return;
      if (location.hash === "#/" + link.dataset.char) applyRoute();
    });

    el.tagPanel.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip");
      if (!chip) return;
      toggleChip(Number(chip.dataset.flat), chip.dataset.cat);
    });

    [el.pagerBottom].forEach((node) => {
      node.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-page]");
        if (!btn || btn.disabled) return;
        goToPage(btn.dataset.page);
      });
      node.addEventListener("change", (event) => {
        const select = event.target.closest(".page-size-select");
        if (!select) return;
        const size = Number(select.value);
        if (!PAGE_SIZES.includes(size)) return;
        state.pageSize = size;
        state.page = 1;
        storageSet("nai-page-size", String(size));
        renderGrid();
        scrollToGallery();
      });
    });

    el.grid.addEventListener(
      "error",
      (event) => {
        const img = event.target;
        if (!img || img.tagName !== "IMG") return;
        if (window.GhImg && window.GhImg.advance(img)) return;
        if (img.dataset.fallback) {
          markBroken(img);
          return;
        }
        img.dataset.fallback = "1";
        img.src = CONFIG.fallback;
      },
      true
    );

    el.grid.addEventListener(
      "load",
      (event) => {
        const img = event.target;
        if (img && img.tagName === "IMG") img.classList.add("is-loaded");
      },
      true
    );

    el.grid.addEventListener("click", async (event) => {
      const btn = event.target.closest(".copy-btn");
      if (!btn) return;
      try {
        const absolute = new URL(btn.dataset.url, location.href).href;
        await copyText(absolute);
        toast("图片链接已复制");
      } catch (err) {
        toast("复制失败，请手动复制");
      }
    });

    el.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      applySearch();
    });

    el.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        el.searchInput.value = "";
        state.query = "";
        state.page = 1;
        render();
        el.searchInput.blur();
      }
    });

    el.clearFilters.addEventListener("click", resetFilters);
    el.emptyReset.addEventListener("click", resetFilters);
    el.retryBtn.addEventListener("click", () => location.reload());
    el.themeToggle.addEventListener("click", cycleTheme);

    document.addEventListener("keydown", (event) => {
      const tag = document.activeElement && document.activeElement.tagName;
      if (event.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        event.preventDefault();
        el.searchInput.focus();
        el.searchInput.select();
      }
    });
  }

  async function init() {
    el.searchForm = $("searchForm");
    el.searchInput = $("searchInput");
    el.sidebarNav = $("sidebarNav");
    el.subTabs = $("subTabs");
    el.tagPanel = $("tagPanel");
    el.grid = $("grid");
    el.pagerBottom = $("pagerBottom");
    el.resultCount = $("resultCount");
    el.clearFilters = $("clearFilters");
    el.emptyState = $("emptyState");
    el.emptyReset = $("emptyReset");
    el.errorState = $("errorState");
    el.errorMsg = $("errorMsg");
    el.retryBtn = $("retryBtn");
    el.toast = $("toast");
    el.themeToggle = $("themeToggle");
    el.themeIcon = $("themeIcon");

    const storedSize = Number(storageGet("nai-page-size"));
    if (PAGE_SIZES.includes(storedSize)) state.pageSize = storedSize;

    applyRepoLinks();
    applyTheme(storageGet("nai-theme") || "auto");
    if (window.GhImg) {
      window.GhImg.configure({ repo: CONFIG.repo });
      window.GhImg.decorate(document.querySelectorAll(".hero-visual img"));
      window.GhImg.start();
    }
    bindEvents();
    setupReveal();
    el.grid.innerHTML = skeletonMarkup(8);

    try {
      const [manifest, tagDimensions] = await Promise.all([
        fetchJSON(CONFIG.dataBase + "manifest.json"),
        fetchJSON(CONFIG.tagDimensions)
      ]);
      if (!Array.isArray(manifest) || !manifest.length) throw new Error("manifest 为空");

      state.manifest = manifest;
      state.tagDimensions = tagDimensions;
      const loaded = await Promise.all(manifest.map((meta) => loadChar(meta)));
      loaded.forEach((data) => state.chars.set(data.meta.id, data));

      renderStats();
      applyRoute();
    } catch (err) {
      el.grid.innerHTML = "";
      el.pagerBottom.hidden = true;
      el.errorState.hidden = false;
      el.errorMsg.textContent = "数据加载失败：" + (err && err.message ? err.message : err);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
