# 🍼🐲 NaiLoong · 奶-hub

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapull.com)
[![Data Linter](https://img.shields.io/badge/CI-Data%20Linter-blue?logo=github)](../../actions)
[![Static Site](https://img.shields.io/badge/Static-SPA%20%2B%20zero%20build-8dd6ff?logo=github)](./index.html)
[![Repo Size](https://img.shields.io/github/repo-size/lin-alg/NaiLoong?color=blue)](https://github.com)

奶龙表情合集，也是一个可以从零练习 GitHub 协作的开源项目。社区图片统一由贡献者公开 Fork 的 `image` 分支托管，主仓库通过 JSON 汇总展示。

## 🧭 按你的目标开始

- **只想分享表情，不想碰 Git：**去[社区投稿评论区](docs/meme-submissions.md)，按格式在置顶 Issue 下留言并上传图片。
- **想练习 GitHub 并亲自提交：**看[新手 GitHub 投稿教程](docs/github-beginner-guide.md)，从 Fork、Git Bash 到发 PR 一步步完成。
- **想改进网站或项目本身：**看[项目结构与开发指南](docs/project-maintainers-guide.md)，了解数据、前端和自动检查。
- **贡献规则与入口索引：**[贡献指南](CONTRIBUTING.md)。

---

## ✨ 特性

- 卡片式表情墙，深色为主，可切跟随系统 / 浅色主题
- 角色侧边栏与分类 Tab 由 `data/manifest.json` 自动生成，加角色不用改代码
- 搜索按 <kbd>Enter</kbd> 执行，标题 + 标签一起匹配，`/` 键唤起搜索框，搜完自动滚到表情库
- 动图 / 静态图分页，每页 4 / 8 / 16 / 32 / 64 条可选，偏好会记在本地
- 标签按维度分组筛选，侧边栏与 Tab 的计数跟随搜索结果更新
- 图片懒加载；GitHub 图片自动探测直连 / gh-proxy 等代理的连通性，选能通的路走，失败逐路回退，最后才换兜底图
- PR 上 CI 运行数据校验、标签解析测试和重复 URL 检查

## 🗂️ 目录结构

```text
NaiLoong/
├── .github/
│   ├── workflows/
│   │   ├── pr-check.yml             # PR 数据校验与测试
│   │   └── deploy.yml               # GitHub Pages 自动化发布
│   ├── ISSUE_TEMPLATE/
│   │   ├── config.yml               # 引导到投稿帖或项目反馈模板
│   │   └── project_feedback.md     # 网站问题与项目建议模板
│   └── pull_request_template.md     # 新手 PR 提交自检清单
├── data/                            # 数据
│   ├── manifest.json                # 全站角色总纲目录
│   └── <role-id>/                   # 每个角色一个目录
│       ├── animated.json            # 动图分类文件
│       ├── static.json              # 静态图分类文件
│       └── tags.json                # 标签维度与取值表
├── docs/                            # 按人群拆分的贡献与开发指南
├── scripts/validate_data.py         # 可本地运行的数据结构校验器
├── tests/                            # 数据校验与标签解析测试
├── assets/
│   ├── css/style.css                # GitHub 设计系统风格样式
│   ├── js/app.js                    # 核心驱动：动态渲染、路由与交互
│   ├── js/search.js                 # 毫秒级多维标签搜索器
│   ├── js/ghimg.js                  # GitHub 图片代理探测与逐路回退
│   ├── icons/                       # Favicon 等小图标
│   └── placeholders/                # 示例占位图（提交真实表情时会逐步替换）
├── index.html                       # 纯前端单页骨架 (SPA)
├── CONTRIBUTING.md                  # 贡献入口总览
├── AGENTS.md                        # AI/协作者开发约定与待确认事项
├── LICENSE                          # MIT 开源许可证
└── README.md                        # 你正在看的文档
```

## 🚀 本地预览

静态站，无需构建，起个本地服务器即可：

```bash
python -m http.server 8080
# 打开 http://localhost:8080
```

## 数据规范

### 1. 总纲 `data/manifest.json`

```json
[
  {
    "id": "naiwa",
    "name": "奶蛙",
    "icon": "🍼🐸",
    "subcategories": [
      { "id": "animated", "name": "动图", "file": "naiwa/animated.json" },
      { "id": "static", "name": "静态图", "file": "naiwa/static.json" }
    ]
  }
]
```

角色 `id` 与其 `data/<role-id>/` 目录名相同；角色 ID 和分类 ID 使用小写英文、数字和连字符，并在各自作用域内唯一。`subcategories[].file` 是相对 `data/` 的 JSON 数组文件路径。

### 2. 表情条目 `animated.json` / `static.json`

```json
[
  { "title": "奶蛙狂笑", "tags": [2, 0, 0], "url": "https://github.com/你的用户名/NaiLoong/blob/image/assets/memes/laugh.png" }
]
```

| 字段 | 类型 | 说明 |
| :--- | :--- | : |
| `title` | string | 表情名称，必填 |
| `tags` | number[] 或 object | 数组按 `tags.json` 维度顺序逐维填写本地序号，可用 `null` 表示未知；也支持 `{ "smile": 2 }` 形式的维度对象 |
| `url` | string | 新投稿使用自己公开 Fork 的 `NaiLoong/blob/image/文件路径` 链接，不使用其他图床 |

### 3. 标签表 `tags.json`

```json
{
  "smile": { "0": "轻松绷住", "1": "憋笑", "2": "大笑" },
  "age limit": { "0": "老少咸宜", "1": "朋友整活", "2": "重口" },
  "artistic merit": { "0": "下里巴人", "1": "日常", "2": "阳春白雪" }
}
```

数组中每个位置对应一个维度，维度顺序与 `tags.json` 一致；填该维度标签的本地序号，不要跨维度展平：

| 维度 | 序号 0 | 序号 1 | 序号 2 |
| :--- | :--- | :--- | :--- |
| `smile` | 轻松绷住 | 憋笑 | 大笑 |
| `age limit` | 老少咸宜 | 朋友整活 | 重口 |
| `artistic merit` | 下里巴人 | 日常 | 阳春白雪 |

所以 `"tags": [2, 0, 1]` = 大笑 + 老少咸宜 + 日常；`[2, null, 1]` 表示年龄限制暂未确定。维度内序号、标签名称都查看该角色自己的 `tags.json`。

维度内序号是非负整数；维度名和标签文字应非空且不能重复。修改维度或已有标签时，先检查同角色所有数据文件，避免旧序号改变含义。

## 🤝 贡献与维护

- **只分享表情：**在[共享投稿 Issue 评论区](docs/meme-submissions.md)上传图片，不需要 Git 或 JSON。
- **自己提交表情：**跟随[GitHub 新手投稿教程](docs/github-beginner-guide.md)，包含 Fork、Git Bash、分支、PR、更新他人条目和冲突解决。
- **修改网站或数据系统：**查看[项目结构与开发指南](docs/project-maintainers-guide.md)。
- 本地检查：`python scripts/validate_data.py` 和 `python -m unittest discover -s tests -v`。
- 视觉参考：[github-design-system-analysis.md](./github-design-system-analysis.md)。

## 🗳️ 贡献者公约

- 投稿应符合社区规则并尊重内容来源
- 一个 PR 尽量只做一件事（一个角色 / 一类改动），方便 review

---

[![GitHub Pages](https://img.shields.io/badge/Status-Online-success?logo=github)](https://github.com)
[![Contributors](https://img.shields.io/github/contributors/lin-alg/NaiLoong?color=orange)](https://github.com)
[![Stars](https://img.shields.io/github/stars/lin-alg/NaiLoong?style=social)](https://github.com)
