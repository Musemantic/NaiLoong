(function () {
  "use strict";

  const state = { scan: null, roles: [], items: [], suggestions: new Map(), aiSuggested: new Set(), busy: false, dirty: false };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
  const typeLabels = { added: "新增", updated: "更新", deleted: "已删除" };
  const modelDefaults = { openai: "gpt-6-astra", anthropic: "claude-sonnet-5-5", google: "gemini-2.5-flash" };

  async function api(path, body) {
    const response = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store"
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "本地编辑器请求失败。");
    return result;
  }

  function toast(message) {
    const node = $("toast");
    node.textContent = message;
    node.hidden = false;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => { node.hidden = true; }, 3600);
  }

  function setBusy(button, active, label) {
    if (active) {
      button.dataset.label = button.textContent.trim();
      button.textContent = label;
      button.classList.add("is-busy");
      button.disabled = true;
    } else {
      button.textContent = button.dataset.label || button.textContent;
      button.classList.remove("is-busy");
      button.disabled = false;
    }
  }

  function setFlow(active, complete = false) {
    document.querySelectorAll(".git-flow li").forEach((node, index) => {
      node.classList.toggle("flow-active", !complete && index === active);
      node.classList.toggle("flow-done", complete || index < active);
      if (!complete && index === active) node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
    });
  }

  function lockReview(active) {
    state.busy = active;
    $("reviewFields").disabled = active;
    for (const id of ["scanButton", "commitCount", "changeFilter", "selectAllButton", "provider", "modelName", "apiKey", "batchSize", "requestInterval", "retryCount", "annotateButton"]) $(id).disabled = active;
    syncSummary();
  }

  function activeRole(item) {
    const suggestion = state.suggestions.get(item.id);
    const roleId = suggestion && Object.prototype.hasOwnProperty.call(suggestion, "role_id")
      ? suggestion.role_id : item.role_id;
    return state.roles.find((role) => role.id === roleId) || null;
  }

  function tagsToArray(value, role) {
    const dimensions = role ? Object.entries(role.tags) : [];
    if (Array.isArray(value)) return dimensions.map((_, index) => {
      const tag = value[index];
      return Number.isInteger(tag) && Object.prototype.hasOwnProperty.call(dimensions[index][1], String(tag)) ? tag : null;
    });
    if (value && typeof value === "object") return dimensions.map(([dimension, values]) => {
      const tag = value[dimension];
      if (Number.isInteger(tag) && Object.prototype.hasOwnProperty.call(values, String(tag))) return tag;
      if (typeof tag === "string") {
        const found = Object.entries(values).find(([, label]) => label === tag);
        if (found) return Number(found[0]);
      }
      return null;
    });
    return dimensions.map(() => null);
  }

  function activeEntry(item) {
    const suggestion = state.suggestions.get(item.id) || {};
    const old = item.entry || {};
    const role = activeRole(item);
    return {
      title: Object.prototype.hasOwnProperty.call(suggestion, "title") ? suggestion.title : (old.title || ""),
      tags: Object.prototype.hasOwnProperty.call(suggestion, "tags") ? suggestion.tags : tagsToArray(old.tags, role)
    };
  }

  function roleOptions(selected) {
    return '<option value="">选择角色</option>' + state.roles.map((role) =>
      '<option value="' + esc(role.id) + '"' + (role.id === selected ? " selected" : "") + '>' +
      esc((role.icon ? role.icon + " " : "") + role.name) + " · " + esc(role.id) + "</option>"
    ).join("");
  }

  function categoryOptions(role, selected) {
    if (!role) return '<option value="' + esc(selected || "") + '">' +
      esc(selected === "animated" ? "动图 · 选择角色后匹配分类" : selected === "static" ? "静态图 · 选择角色后匹配分类" : "选择角色后匹配分类") + "</option>";
    return role.categories.map((category) =>
      '<option value="' + esc(category.id) + '"' + (category.id === selected ? " selected" : "") + '>' +
      esc(category.name) + " · " + esc(category.id) + "</option>"
    ).join("");
  }

  function categoryForMedia(role, mediaType) {
    if (!role) return null;
    const exact = role.categories.find((category) => category.id === mediaType);
    if (exact) return exact;
    const hints = mediaType === "animated"
      ? ["动图", "动画", "gif", "animated", "motion"]
      : ["静态图", "静态", "图片", "static", "still"];
    return role.categories.find((category) => {
      const value = (category.id + " " + category.name).toLowerCase();
      return hints.some((hint) => value.includes(hint));
    }) || role.categories[0] || null;
  }

  function tagOptions(role, itemId, current) {
    if (!role) return "";
    return Object.entries(role.tags).map(([dimension, values], dimensionIndex) => {
      const selected = Array.isArray(current) ? current[dimensionIndex] : null;
      const controlId = "tag-" + itemId + "-" + dimensionIndex;
      const translated = state.scan && state.scan.metadata.tag_translations && state.scan.metadata.tag_translations[dimension];
      return '<label class="field"><span>' + esc(translated ? translated.zh : dimension) + '</span>' +
        '<select data-tag-index="' + dimensionIndex + '" id="' + esc(controlId) + '"><option value="">未知</option>' +
        Object.entries(values).map(([localId, label]) =>
          '<option value="' + esc(localId) + '"' + (String(selected) === localId ? " selected" : "") + '>' +
          esc(localId + ": " + label) + "</option>"
        ).join("") + "</select></label>";
    }).join("");
  }

  function diffCard(item) {
    const checked = item.kind !== "deleted";
    const entry = activeEntry(item);
    const role = activeRole(item);
    const suggestion = state.suggestions.get(item.id);
    const categoryId = suggestion && suggestion.category_id !== undefined
      ? suggestion.category_id : (item.category_id || item.category_hint);
    const oldEntry = item.entry || {};
    let body = "";

    if (item.kind === "deleted") {
      body = (item.old_preview ? '<div class="preview-pair"><div class="preview-frame"><span class="preview-label">删除前</span><img src="' +
        esc(item.old_preview) + '" alt="删除前图片预览" loading="lazy"></div></div>' : "") +
        '<div class="deleted-diff"><div><strong>删除前</strong>' + esc(item.path) +
        (item.old_record ? '<br><span>' + esc(item.old_record.entry.title || "已有记录") + '</span>' : "") +
        '</div><div><strong>删除后</strong><span>image 分支上已不存在此文件</span></div></div>' +
        '<div class="delete-warning"><p>这张图片在本次提交中被删除。若是误删，请先回到 image 分支恢复文件，再重新扫描。</p>' +
        '<p>先停止编辑器并运行 <code>git switch image</code>，然后：<br><code>git pull --ff-only origin image</code><br>' +
        '<code>git restore --source=' + esc(item.restore_ref || (state.scan && state.scan.base)) + ' -- &quot;' + esc(item.path) +
        '&quot;</code><br><code>git add &quot;' + esc(item.path) + '&quot;</code><br>' +
        '<code>git commit -m &quot;fix: 恢复误删图片&quot;</code> 和 <code>git push</code>。完成后切回投稿工作分支并更新本地 image。' +
        '也可打开 <a href="https://github.com/' + esc(state.scan.owner) + '/NaiLoong/blob/' +
        esc(item.restore_ref || state.scan.base) + '/' + encodeURIComponent(item.path).replace(/%2F/g, "/") +
        '" target="_blank" rel="noopener noreferrer">删除前版本</a>，从网页下载后放回原路径再提交。</p>' +
        (item.old_record ? '<label><input type="checkbox" data-remove-record="' + esc(item.id) + '"> 同时从网站数据移除此条记录</label>' : "") +
        "</div>";
    } else {
      const before = item.kind === "updated" ? item.old_preview : "";
      body = '<div class="preview-pair">' +
        (before ? '<div class="preview-frame"><span class="preview-label">之前</span><img src="' + esc(before) + '" alt="旧图片预览" loading="lazy"></div>' : "") +
        '<div class="preview-frame"><span class="preview-label">' + (before ? "之后" : "预览") + '</span>' +
        '<img src="' + esc(item.preview) + '" alt="' + esc(item.path) + '" loading="lazy"></div></div>' +
        '<div class="diff-fields">' +
        (item.kind === "updated" ? '<div class="field field-wide"><label>原条目</label><div class="old-new"><span class="old-value">' +
          esc(oldEntry.title || "无标题") + " · " + esc(oldEntry.url || "") + '</span><span class="diff-arrow">→</span><span class="new-value">' +
          esc(item.url) + '</span></div><span class="field-note">原标签与来源信息会保留，只更新这张图片的固定 commit URL。</span></div>' :
          '<div class="field field-wide"><label>将新增图片 URL</label><div class="new-value">' + esc(item.url) + '</div></div>') +
        '<div class="field"><label for="role-' + esc(item.id) + '">角色</label><select data-role-id="' + esc(item.id) + '" id="role-' + esc(item.id) + '">' +
          roleOptions(role ? role.id : "") + '</select></div>' +
        '<div class="field"><label for="category-' + esc(item.id) + '">分类 · ' + esc(item.media_type === "animated" ? "动图" : "静态图") + '</label>' +
          '<select data-category-id="' + esc(item.id) + '" id="category-' + esc(item.id) + '"' + (!role ? " disabled" : "") + '>' + categoryOptions(role, categoryId) + '</select></div>' +
        '<div class="field field-wide"><label for="title-' + esc(item.id) + '">标题</label><input data-title-id="' + esc(item.id) + '" id="title-' + esc(item.id) + '" type="text" value="' +
          esc(entry.title) + '" placeholder="输入表情标题"></div>' +
        '<div class="tags-editor" data-tags-for="' + esc(item.id) + '">' +
          (role ? tagOptions(role, item.id, entry.tags) : '<p class="field-note field-wide">选择角色后显示对应标签。</p>') + '</div>' +
        (state.aiSuggested.has(item.id) ? '<p class="field-note field-wide is-ai">已填入 AI 建议，请核对标题和标签。</p>' : "") +
        '</div>';
    }
    let reason = item.kind === "updated" ? item.change_reason : (item.change_reason || "");
    const sizeLabel = (item.size_bytes / (1024 * 1024)).toFixed(2) + " MB";
    const oversized = item.size_bytes > 5 * 1024 * 1024;
    if (oversized) reason = "超出 5 MB 上限 · " + sizeLabel;
    else if (item.kind !== "deleted") reason += " · " + sizeLabel;
    return '<article class="change-card" data-kind="' + esc(item.kind) + '" data-item-id="' + esc(item.id) + '">' +
      '<header class="change-head"><div class="change-ident">' +
      '<input class="change-check" type="checkbox" data-select-id="' + esc(item.id) + '"' + (checked ? " checked" : "") + (item.kind === "deleted" ? " disabled" : "") + ' aria-label="选择 ' + esc(item.path) + '">' +
      '<span class="change-kind">' + esc(typeLabels[item.kind]) + '</span><code class="change-path">' + esc(item.path) + '</code></div>' +
      '<span class="change-reason' + (oversized ? " is-size-error" : "") + '">' + esc(reason) + '</span></header><div class="change-body">' + body + '</div></article>';
  }

  function render() {
    const filter = $("changeFilter").value;
    const visible = state.items.filter((item) => filter === "all" || item.kind === filter);
    const groups = $("changeGroups");
    groups.innerHTML = visible.length ? ["added", "updated", "deleted"].map((kind) => {
      const entries = visible.filter((item) => item.kind === kind);
      if (!entries.length) return "";
      const title = kind === "added" ? "新增文件" : kind === "updated" ? "更新与重命名" : "删除提醒";
      return '<section class="change-group" aria-label="' + title + '"><header><h3>' + title +
        '</h3><span>' + entries.length + '</span></header>' + entries.map(diffCard).join("") + "</section>";
    }).join("") : '<p class="scan-note">此类别没有变更。</p>';
    for (const item of state.items) {
      const check = groups.querySelector('[data-select-id="' + item.id + '"]');
      if (check) check.checked = item.selected !== false;
      const remove = groups.querySelector('[data-remove-record="' + item.id + '"]');
      if (remove) remove.checked = item.remove_record === true;
    }
    $("countAdded").textContent = state.items.filter((item) => item.kind === "added").length;
    $("countUpdated").textContent = state.items.filter((item) => item.kind === "updated").length;
    $("countDeleted").textContent = state.items.filter((item) => item.kind === "deleted").length;
    $("reviewWorkspace").hidden = state.items.length === 0;
    $("emptyReview").hidden = state.items.length !== 0;
    $("applySuccess").hidden = true;
    syncSummary();
  }

  function syncSummary() {
    const selectedItems = state.items.filter((item) => item.selected !== false && item.kind !== "deleted");
    const selectedCount = selectedItems.length;
    const removeCount = state.items.filter((item) => item.remove_record === true).length;
    const incomplete = selectedItems.filter((item) => {
      const role = activeRole(item);
      const draft = state.suggestions.get(item.id) || {};
      return !role || !activeEntry(item).title.trim() || !role.categories.some((category) => category.id === (draft.category_id || item.category_id || item.category_hint));
    }).length;
    const oversized = selectedItems.filter((item) => item.size_bytes > 5 * 1024 * 1024).length;
    $("applySummary").textContent = selectedCount + " 条图片变更已勾选" + (removeCount ? "，另移除 " + removeCount + " 条记录" : "") +
      (incomplete ? "；" + incomplete + " 条需补齐角色、分类或标题" : "") + (oversized ? "；" + oversized + " 张超过 5 MB，需压缩后重扫或取消勾选" : "") + "。";
    $("applyButton").disabled = state.busy || !state.scan || !state.scan.scan_id || selectedCount + removeCount === 0 || incomplete > 0 || oversized > 0;
  }

  function preserveEdits() {
    if (!state.items.length) return;
    for (const item of state.items) {
      if (item.kind === "deleted") continue;
      const roleSelect = document.querySelector('[data-role-id="' + item.id + '"]');
      const categorySelect = document.querySelector('[data-category-id="' + item.id + '"]');
      const titleInput = document.querySelector('[data-title-id="' + item.id + '"]');
      if (!roleSelect || !titleInput) continue;
      let suggestion = state.suggestions.get(item.id) || {};
      suggestion.role_id = roleSelect.value || null;
      suggestion.category_id = categorySelect && categorySelect.value;
      suggestion.title = titleInput.value;
      const tags = Array.from(document.querySelectorAll('[data-tags-for="' + item.id + '"] [data-tag-index]'))
        .map((select) => select.value === "" ? null : Number(select.value));
      suggestion.tags = tags;
      state.suggestions.set(item.id, suggestion);
    }
    for (const item of state.items) {
      const selected = document.querySelector('[data-select-id="' + item.id + '"]');
      if (selected) item.selected = selected.checked;
      const remove = document.querySelector('[data-remove-record="' + item.id + '"]');
      if (remove) item.remove_record = remove.checked;
    }
  }

  async function loadProject() {
    const status = $("scanStatus");
    try {
      const result = await api("/api/project");
      state.roles = result.roles;
      const onWorkBranch = typeof result.work_branch === "string" && result.work_branch.startsWith("meme/");
      $("scanButton").disabled = !onWorkBranch;
      status.textContent = result.image_head
        ? "本地仓库已连接，可以扫描 image 分支。"
        : "本地仓库已连接，但还没有本地 image 分支。";
      $("branchName").textContent = result.work_branch || "detached HEAD";
      $("headSha").textContent = result.image_head ? "image · " + result.image_head : "本地 image 分支尚未建立";
      setFlow(onWorkBranch && result.image_head ? 1 : 0);
      if (!onWorkBranch || !result.image_head) {
        $("scanError").textContent = "当前分支是 " + (result.work_branch || "detached HEAD") +
          (!onWorkBranch ? "。请先切换到 meme/... 投稿工作分支，再刷新页面。" :
            "。没有本地 image 时：git fetch origin，然后 git branch --track image origin/image；若 Fork 中也没有 image，先按教程提交图片。");
        $("scanButton").disabled = true;
        $("scanError").hidden = false;
      } else {
        $("scanError").hidden = true;
      }
    } catch (error) {
      status.textContent = error.message;
      $("scanError").textContent = "请在仓库根目录运行 python scripts/data_editor.py data，再刷新此页面。\n" + error.message;
      $("scanError").hidden = false;
    }
  }

  async function scan() {
    if (state.busy) return;
    if (state.dirty && !window.confirm("重新扫描会清空当前尚未写入的编辑和 AI 建议，继续吗？")) return;
    const button = $("scanButton");
    const errorNode = $("scanError");
    errorNode.hidden = true;
    preserveEdits();
    lockReview(true);
    setBusy(button, true, "正在扫描…");
    $("scanStatus").textContent = "比较最近提交的文件变化…";
    try {
      const result = await api("/api/scan", { commit_count: Number($("commitCount").value) });
      state.scan = result;
      state.roles = result.metadata.roles;
      state.items = result.changes.map((item) => ({ ...item, selected: item.kind !== "deleted", remove_record: false }));
      state.suggestions.clear();
      state.aiSuggested.clear();
      state.dirty = false;
      $("changeFilter").value = "all";
      $("aiStatus").textContent = "";
      $("applyError").hidden = true;
      $("branchName").textContent = result.work_branch;
      $("headSha").textContent = "读取 image · " + result.head.slice(0, 12);
      $("scanSource").textContent = "图片来源：image · " + result.base.slice(0, 10) + " → " + result.head.slice(0, 10) + " / JSON 写入：" + result.work_branch +
        "。扫描只读取本地提交，请确认这些图片已推送到公开 Fork。";
      $("scanSource").hidden = false;
      $("scanStatus").textContent = "已扫描 " + result.commit_count + " 个 commit · 基准 " + result.base.slice(0, 10);
      $("applySuccess").hidden = true;
      setFlow(result.changes.length ? 2 : 1);
      render();
    } catch (error) {
      errorNode.textContent = error.message;
      errorNode.hidden = false;
      $("scanStatus").textContent = "扫描失败";
    } finally {
      setBusy(button, false);
      lockReview(false);
      button.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M7 2.5a4.5 4.5 0 1 0 2.9 7.94L13 13.5M7 4.5v3m-1.5-1.5h3"/></svg>扫描 image 分支';
    }
  }

  async function annotate() {
    if (state.busy || !state.scan || !state.scan.scan_id) return;
    preserveEdits();
    const selected = state.items.filter((item) => item.kind !== "deleted" && item.selected).map((item) => item.id);
    if (!selected.length) { toast("请先选择要标注的图片。"); return; }
    const button = $("annotateButton");
    const status = $("aiStatus");
    const keyInput = $("apiKey");
    if (!keyInput.value.trim() || !$("modelName").value.trim()) { toast("请填写 API 密钥和模型名称。"); return; }
    status.className = "ai-status";
    status.textContent = "正在准备角色参考图和图片…";
    const payload = {
      scan_id: state.scan.scan_id,
      item_ids: selected,
      provider: $("provider").value,
      api_key: keyInput.value,
      model: $("modelName").value.trim(),
      batch_size: Number($("batchSize").value),
      interval: Number($("requestInterval").value),
      retries: Number($("retryCount").value)
    };
    keyInput.value = "";
    lockReview(true);
    setBusy(button, true, "正在请求…");
    try {
      const result = await api("/api/annotate", payload);
      keyInput.value = "";
      for (const suggestion of result.suggestions || []) {
        const item = state.items.find((value) => value.path === suggestion.path);
        if (!item) continue;
        const previous = state.suggestions.get(item.id) || {};
        const suggestedRole = item.kind === "updated" ? (previous.role_id || item.role_id) : (suggestion.role_id || previous.role_id || null);
        const role = state.roles.find((value) => value.id === suggestedRole) || null;
        let tags = Array.isArray(suggestion.tags) ? suggestion.tags : [];
        if (item.kind === "updated") tags = previous.tags || tagsToArray(item.entry && item.entry.tags, role);
        const category = categoryForMedia(role, item.media_type);
        state.suggestions.set(item.id, {
          title: suggestion.title || previous.title || (item.entry && item.entry.title) || "",
          role_id: suggestedRole,
          category_id: role && role.id === previous.role_id && previous.category_id ? previous.category_id : (item.kind === "updated" ? item.category_id : (category ? category.id : "")),
          tags: tagsToArray(tags, role)
        });
        state.aiSuggested.add(item.id);
      }
      state.dirty = state.dirty || state.aiSuggested.size > 0;
      render();
      const problems = (result.errors || []).map((value) => value.paths.join(", ") + "：" + value.error);
      status.textContent = "已收到 " + (result.suggestions || []).length + " 条建议。" +
        (problems.length ? "部分失败：" + problems.join("；") : "请逐项核对结果。");
      if (problems.length) status.classList.add("is-error");
      else status.classList.add("is-success");
    } catch (error) {
      keyInput.value = "";
      status.textContent = error.message;
      status.classList.add("is-error");
    } finally {
      payload.api_key = "";
      setBusy(button, false);
      lockReview(false);
      button.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m8 1 .9 4.1L13 4l-2.2 3.5L15 9l-4.3.5L12 14l-3.5-2.2L6 15l-.4-4.3L1 12l2.2-3.5L0 6l4.3-.4L3 1l3.5 2.2z"/></svg>开始批量标注';
    }
  }

  function decisions() {
    preserveEdits();
    return state.items.map((item) => {
      if (item.kind === "deleted") return { id: item.id, selected: false, remove_record: item.remove_record };
      const suggestion = state.suggestions.get(item.id) || {};
      const role = activeRole(item);
      return {
        id: item.id,
        selected: item.selected,
        role_id: suggestion.role_id || item.role_id || "",
        category_id: suggestion.category_id || item.category_id || item.category_hint || "",
        title: suggestion.title !== undefined ? suggestion.title : ((item.entry && item.entry.title) || ""),
        tags: Array.isArray(suggestion.tags) ? suggestion.tags :
          (Array.isArray(item.entry && item.entry.tags) ? item.entry.tags : Array(role ? Object.keys(role.tags).length : 0).fill(null))
      };
    });
  }

  async function apply() {
    if (state.busy || !state.scan || !state.scan.scan_id) return;
    const entries = decisions();
    const selected = entries.filter((item) => item.selected).length;
    const removed = entries.filter((item) => item.remove_record).length;
    if (!selected && !removed) return;
    const confirmation = "将写入 " + selected + " 条图片变更" + (removed ? "，并删除 " + removed + " 条已删除图片记录" : "") +
      "。数据校验失败时会自动恢复。继续吗？";
    if (!window.confirm(confirmation)) return;
    const button = $("applyButton");
    $("applyError").hidden = true;
    lockReview(true);
    setFlow(3);
    setBusy(button, true, "校验并写入…");
    try {
      const result = await api("/api/apply", {
        scan_id: state.scan.scan_id,
        decisions: entries
      });
      setFlow(3, true);
      $("scanStatus").textContent = "已写入并通过完整数据校验。";
      state.scan.scan_id = "";
      state.dirty = false;
      toast("写入完成：" + result.result.written_files.join("、"));
      $("reviewWorkspace").hidden = true;
      $("emptyReview").hidden = true;
      $("applySuccess").hidden = false;
      $("writtenFiles").textContent = result.result.written_files.join("、") || "所选删除记录已处理。";
      const shellQuote = (value) => "'" + value.replace(/'/g, "'\\''") + "'";
      $("nextCommands").textContent = "git status\ngit add -- " + result.result.written_files.map((file) => shellQuote("data/" + file)).join(" ") +
        '\ngit diff --staged\ngit commit -m "feat: 添加表情记录"\ngit push -u origin ' + shellQuote(state.scan.work_branch);
      $("applySuccess").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
      setFlow(2);
      $("applyError").textContent = error.message;
      $("applyError").hidden = false;
      toast(error.message);
    } finally {
      setBusy(button, false);
      lockReview(false);
      button.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.3 6.2 11.5 13 4.5M2 14h12"/></svg>确认并写入数据';
    }
  }

  function bind() {
    $("scanButton").addEventListener("click", scan);
    $("changeFilter").addEventListener("change", () => { preserveEdits(); render(); });
    $("selectAllButton").addEventListener("click", () => {
      preserveEdits();
      state.dirty = true;
      state.items.filter((item) => item.kind !== "deleted").forEach((item) => { item.selected = true; });
      render();
    });
    $("changeGroups").addEventListener("change", (event) => {
      state.dirty = true;
      const roleSelect = event.target.closest("[data-role-id]");
      if (roleSelect) {
        preserveEdits();
        const item = state.items.find((value) => value.id === roleSelect.dataset.roleId);
        const suggestion = state.suggestions.get(item.id) || {};
        suggestion.role_id = roleSelect.value || null;
        const role = state.roles.find((value) => value.id === roleSelect.value);
        const hinted = categoryForMedia(role, item.media_type);
        suggestion.category_id = hinted ? hinted.id : "";
        suggestion.tags = role ? Object.keys(role.tags).map(() => null) : [];
        state.suggestions.set(item.id, suggestion);
        render();
        return;
      }
      const selection = event.target.closest("[data-select-id]");
      if (selection) {
        const item = state.items.find((value) => value.id === selection.dataset.selectId);
        if (item) item.selected = selection.checked;
      }
      const remove = event.target.closest("[data-remove-record]");
      if (remove) {
        const item = state.items.find((value) => value.id === remove.dataset.removeRecord);
        if (item) item.remove_record = remove.checked;
      }
      preserveEdits();
      syncSummary();
    });
    $("changeGroups").addEventListener("input", () => { state.dirty = true; preserveEdits(); syncSummary(); });
    window.addEventListener("beforeunload", (event) => { if (state.dirty || state.busy) { event.preventDefault(); event.returnValue = ""; } });
    $("provider").addEventListener("change", () => {
      $("modelName").value = modelDefaults[$("provider").value];
    });
    $("annotateButton").addEventListener("click", annotate);
    $("applyButton").addEventListener("click", apply);
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("scanButton").disabled = true;
    bind();
    loadProject();
  });
})();
