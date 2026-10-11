(function () {
  "use strict";

  const steps = [
    {
      title: "准备 Fork 和本地仓库",
      time: "约 5 分钟",
      description: "Fork 之后会在你的 GitHub 账号下建立一份仓库的独立副本。表情图片保存在自己的 image 分支，表情记录则通过另一个工作分支向仓库提交 PR。",
      commands: `# 在 GitHub 上 Fork lin-alg/NaiLoong 后，复制你自己的仓库地址\ngit clone https://github.com/<你的用户名>/NaiLoong.git\ncd NaiLoong\ngit remote add upstream https://github.com/lin-alg/NaiLoong.git\ngit remote -v\ngit config --global user.name "你的 GitHub 用户名"\ngit config --global user.email "你的 GitHub 邮箱"`,
      hint: "把尖括号内容替换为自己的用户名。remote -v 应显示 origin 指向你的 Fork，upstream 指向 lin-alg/NaiLoong。",
      actions: [{ label: "Git for Windows", href: "https://git-scm.com/downloads/win" }, { label: "打开项目仓库", href: "https://github.com/lin-alg/NaiLoong" }],
      extra: "",
      branch: "main"
    },
    {
      title: "同步 main 并创建投稿分支",
      time: "约 2 分钟",
      description: "同步主仓库的最新更改，并创建一个新的工作分支用于本次投稿。下面的 meme/naiwa-laugh 是示例分支名，建议换成能描述本次投稿的名称。",
      commands: `git fetch upstream main\ngit switch main\ngit merge --ff-only upstream/main\ngit push origin main\ngit switch -c meme/naiwa-laugh`,
      hint: "fetch 下载主仓库记录；merge --ff-only 只在可快进时更新；最后一条命令创建并切换到你的 JSON 投稿工作分支。",
      actions: [],
      extra: "你的 origin/main 只保存项目代码和 JSON 记录。不要把 image 分支合并进 main，也不要从 image 分支创建 PR。",
      branch: "main"
    },
    {
      title: "准备本地 image 分支",
      time: "约 1 分钟",
      description: "图片保存在长期公开的 image 分支，表情的修改记录保存在 meme/... 工作分支。首次投稿时通常还没有 image 分支，从当前投稿分支创建它；已有 image 时先更新本地分支。",
      commands: `# Fork 中还没有 image 分支时：\ngit switch -c image`,
      hint: "如果 Fork 上已有 image：运行 git fetch origin，再用 git switch --track origin/image 建立本地分支；若本地已有 image，则 git switch image 后运行 git pull --ff-only origin image。",
      actions: [],
      extra: "完成图片 commit 后，下一步会带你切回 meme/naiwa-laugh。image 分支不要合并进 main。",
      branch: "image"
    },
    {
      title: "一次提交本次所有图片",
      time: "约 3 分钟",
      description: "把新增和替换后的图片放在仓库根目录的 assets/memes/。每张图片不超过 5 MB。建议将所有图片改动用一个 commit 提交，历史更简洁。",
      commands: `# 将本次所有图片复制到 assets/memes/\ngit add assets/memes/\ngit status\ngit commit -m "feat: 添加新表情图片"\ngit push -u origin image\ngit rev-parse HEAD\ngit switch meme/naiwa-laugh`,
      hint: "git status 确认只包含图片。记录 push 后 `git rev-parse HEAD` 命令输出的 commit 哈希。image 分支应长期保持公开并不要删除。",
      actions: [],
      extra: "注意仅应在image分支上提交图片相关的修改。",
      branch: "image"
    },
    {
      title: "扫描图片差异并自动整理记录",
      time: "约 5 分钟",
      description: "切换到meme投稿分支上启动本地浏览器编辑器。默认扫描最近一个 image commit；若连续提交了几次，可改为扫描最近 N 个。新增图片自动得到 URL 和动静分类，已有记录会显示修改前后差异。",
      commands: `python scripts/data_editor.py data`,
      hint: "Windows 若 python 命令不可用，可试 py scripts/data_editor.py data。编辑器自动整理的角色、标题和标签仍可手动更改。",
      actions: [],
      extra: "删除图片会单独提醒，默认保留网站条目；若误删，按界面中的恢复指引处理。用AI批量标注可输入api密钥。AI 会看到角色标签、标题示例和角色 PNG；会用电脑上的 ffmpeg 将 GIF 转成 MP4 并抽取代表帧。api密钥不会保存在磁盘，AI的结果需要人工复核。",
      branch: "work"
    },
    {
      title: "检查 JSON 并创建 Pull Request",
      time: "约 4 分钟",
      description: "写入后的分类文件已经过完整数据校验。提交前再次运行测试，检查暂存区只包含本次表情的修改记录，然后把工作分支推到自己的 Fork 仓库。",
      commands: `python scripts/validate_data.py\npython -m unittest discover -s tests -v\ngit status\ngit add data/naiwa/animated.json\ngit diff --staged\ngit commit -m "feat: 添加奶蛙狂笑表情"\ngit push -u origin meme/naiwa-laugh`,
      hint: "把例子中的数据路径和分支名换成自己的实际值。浏览器PR时选择 base: lin-alg/NaiLoong main，compare: 你的 Fork meme/naiwa-laugh。",
      actions: [{ label: "打开 GitHub PR 页面", href: "https://github.com/lin-alg/NaiLoong/compare" }],
      extra: "查看 Files changed，确认图片没有混入 PR。若整理了投稿区评论图片，把每条原评论的完整链接贴在 PR 描述中。等待检查通过后由维护者审核合并。",
      branch: "work"
    }
  ];

  const $ = (id) => document.getElementById(id);
  let current = 0;

  function renderNav() {
    $("stepNav").innerHTML = steps.map((step, index) =>
      '<li><button type="button" data-step="' + index + '"' + (index === current ? ' aria-current="step"' : "") + '>' +
      '<span class="step-nav-number">' + (index + 1) + '</span><span class="step-nav-name">' + step.title + "</span></button></li>"
    ).join("");
  }

  function render() {
    const step = steps[current];
    $("stepCounter").textContent = "STEP " + (current + 1) + " OF " + steps.length;
    $("lessonTitle").textContent = step.title;
    $("stepTime").textContent = step.time;
    $("stepDescription").textContent = step.description;
    $("commandText").textContent = step.commands;
    $("commandHint").textContent = step.hint;
    $("terminalBlock").hidden = !step.commands;
    $("stepActions").innerHTML = step.actions.map((action) =>
      '<a class="btn btn-secondary" href="' + action.href + '" target="_blank" rel="noopener noreferrer">' + action.label + ' ↗</a>'
    ).join("");
    $("lessonExtra").innerHTML = step.extra ? '<p class="step-callout">' + step.extra + "</p>" : "";
    $("previousStep").disabled = current === 0;
    $("previousStep").style.visibility = current === 0 ? "hidden" : "visible";
    $("nextStep").textContent = current === steps.length - 1 ? "重新查看第 1 步 ↺" : "下一步 →";
    $("lessonProgress").style.width = ((current + 1) / steps.length * 100) + "%";
    document.querySelector(".lesson-progress").setAttribute("aria-valuenow", String(current + 1));
    renderNav();
    const active = document.querySelector(".active-pulse");
    const coordinates = step.branch === "image" ? [148, 80] : step.branch === "work" ? [196, 118] : [150, 38];
    active.setAttribute("cx", coordinates[0]);
    active.setAttribute("cy", coordinates[1]);
  }

  function changeStep(value) {
    current = Math.max(0, Math.min(steps.length - 1, value));
    render();
    $("lessonTitle").focus({ preventScroll: true });
    document.getElementById("lesson").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(steps[current].commands);
    } catch (error) {
      const area = document.createElement("textarea");
      area.value = steps[current].commands;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    const message = $("copyToast");
    message.hidden = false;
    window.clearTimeout(copy.timer);
    copy.timer = window.setTimeout(() => { message.hidden = true; }, 1800);
  }

  document.addEventListener("DOMContentLoaded", () => {
    render();
    $("previousStep").addEventListener("click", () => changeStep(current - 1));
    $("nextStep").addEventListener("click", () => changeStep((current + 1) % steps.length));
    $("copyCommand").addEventListener("click", copy);
    $("stepNav").addEventListener("click", (event) => {
      const button = event.target.closest("[data-step]");
      if (button) changeStep(Number(button.dataset.step));
    });
    document.addEventListener("keydown", (event) => {
      if (event.altKey && event.key === "ArrowRight") changeStep(current + 1);
      if (event.altKey && event.key === "ArrowLeft") changeStep(current - 1);
    });
  });
})();
