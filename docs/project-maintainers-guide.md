# 项目结构与开发指南

本文面向希望改进网页、数据结构、CI 或项目文档的贡献者。项目没有前端构建步骤，网站直接由 GitHub Pages 发布。

## 项目结构

| 路径 | 职责与修改边界 |
| :--- | :--- |
| `index.html` | 页面骨架、导航、搜索区、角色/分类容器和页面文案；数据和列表由 JavaScript 渲染。 |
| `assets/css/style.css` | 全站布局、主题、组件和响应式样式。视觉参考 `github-design-system-analysis.md`。 |
| `assets/js/app.js` | 读取 manifest 和数据、角色/分类路由、渲染、分页、筛选、主题和交互。 |
| `assets/js/search.js` | 标签索引构建、标签格式解析、搜索和筛选逻辑。 |
| `assets/js/ghimg.js` | GitHub 图片 URL 转换、可用图片路由探测和失败回退。 |
| `assets/icons/` | 网站图标。 |
| `assets/placeholders/` | 示例、兜底和当前占位图片；不作为社区投稿的图片来源。 |
| `data/manifest.json` | 角色列表、路由 ID、展示名称、图标和各分类数据文件入口。 |
| `data/<role>/animated.json` | 该角色的动图分类文件。 |
| `data/<role>/static.json` | 该角色的静态图分类文件。 |
| `data/<role>/tags.json` | 该角色的标签维度和维度内标签定义。 |
| `data/tag-translations.json` | 标签维度的中英文显示名称。 |
| `.github/ISSUE_TEMPLATE/` | 网站问题与项目建议模板；表情投稿走共享 Issue 评论区。 |
| `.github/pull_request_template.md` | PR 作者提交前的检查清单。 |
| `.github/workflows/pr-check.yml` | Pull Request 上执行数据校验器和 Python 单元测试。 |
| `.github/workflows/deploy.yml` | 检查数据并将仓库根目录发布到 GitHub Pages。 |
| `scripts/validate_data.py` | 数据、manifest、分类引用、标签和图片地址的仓库级校验。 |
| `tests/` | 数据校验和标签解析的自动化测试；Python 测试使用标准库，搜索测试使用 Node 内置断言。 |
| `docs/` | 面向不同贡献者的投稿、Git 和项目开发说明。 |
| `CONTRIBUTING.md` | 三类参与者的文档入口索引。 |
| `AGENTS.md` | 协作者应遵循的实现约定、校验命令和待确认事项。 |
| `github-design-system-analysis.md` | 现有 UI 设计参考文档。 |
| `LICENSE` | 当前仓库代码的 MIT 许可证。 |

## 数据如何变成页面

1. `app.js` 读取 `data/manifest.json`，按 `id` 建立角色路由。
2. 每个角色的 `subcategories[].file` 指向一个表情 JSON 数组；第一个分类文件所在目录默认提供该角色的 `tags.json`，也可以在 manifest 中显式指定 `tags`。
3. `search.js` 按 `tags.json` 的维度顺序读取每个维度的本地序号，再建立页面筛选索引；数据数组不存跨维度展平索引。tag panel 的维度显示名从 `data/tag-translations.json` 读取。
4. 每条数据的 `url` 由卡片组件作为图片地址加载；`ghimg.js` 仅对 GitHub `blob` / `raw` 图片地址尝试转换和代理回退。

表情条目至少包含非空 `title`、`url` 和 `tags`。`tags` 数组长度与维度数相同，按维度顺序存本地整数序号或 `null`；对象写法使用“维度名 → 本地序号、标签文字或 `null`”。详情见 [README 数据规范](../README.md#数据规范)。

标签维度键新增或改名时，在 `data/tag-translations.json` 同步提供非空的 `en` 和 `zh` 显示名；分类文件中使用的每个维度都必须有对应翻译。

## 新增角色

1. 新建 `data/<role-id>/animated.json`、`static.json`、`tags.json`。空数据文件使用 `[]`。
2. 在 `manifest.json` 追加唯一角色 ID、展示名、图标和分类列表。角色与分类 ID 使用小写英文、数字和连字符；分类文件路径相对 `data/`，例如 `naidan/animated.json`。
3. 角色 ID 与数据目录名保持一致；分类文件使用安全的仓库相对路径，不引用目录外文件。
4. 标签定义应有稳定含义。添加、删除或重新排序维度会改变标签数组位置，必须同步检查该角色全部表情的标签。
5. 本地运行站点，检查新角色路由、分类、图片和筛选器。

## 修改现有数据或标签

- 修复标题、标签或图片时，修改原有条目而不是重复追加；PR 说明旧条目如何定位。
- 同一角色 `tags.json` 的维度顺序对应标签数组位置，维度内部的数字键是本地序号。调整维度顺序会改变数组位置；修改本地序号时也要同步检查该维度的记录。
- 维度名称的中英文显示文本统一维护在 `data/tag-translations.json`，前端按维度键查找中文名称；不要在渲染代码中写死译名。
- 当前页面兼容数字数组和 `{ "维度": 本地序号或标签文字 }` 对象。校验器以这两种格式为正式投稿格式；不要依赖运行时虽然能读取但文档未支持的隐式类型。
- 新投稿的 `url` 必须指向贡献者公开 Fork 中 `image` 分支的文件；推荐 `NaiLoong/blob/image/<path>` 格式。校验器也接受等价 RAW 格式，检查 URL 结构但不联网确认文件是否存在。

## 从投稿 Issue 收录图片

投稿人直接将图片上传到[共享投稿 Issue](https://github.com/lin-alg/NaiLoong/issues/1)评论区，不需要 Fork。整理投稿时，从评论下载图片，上传到处理者自己的公开 Fork 的 `image` 分支，再在 PR 数据记录中引用该分支的图片地址。投稿评论中的附件地址不写入分类文件。

## 本地运行与检查

在仓库根目录执行：

```bash
python -m http.server 8080
```

浏览器打开 `http://localhost:8080`。静态页面通过 HTTP 读取 JSON；直接用 `file://` 打开会遇到浏览器的跨域限制。停止本地服务器按 `Ctrl+C`。

运行与 CI 相同的检查：

```bash
python scripts/validate_data.py
python -m unittest discover -s tests -v
node tests/search.test.js
node tests/ghimg.test.js
```

校验器仅使用 Python 标准库。CI 运行在 Ubuntu；建议本地使用 Python 3.9 或更新版本。

## 自动检查

`.github/workflows/pr-check.yml` 在 Pull Request 上运行三步：

1. `python -m unittest discover -s tests -v`，验证校验器能接受有效数据并拒绝已知错误。
2. `node tests/search.test.js`，验证本地序号、`null`、对象写法、搜索和双语标签展示。
3. `node tests/ghimg.test.js`，验证 blob / RAW 图片地址转换。
4. `python scripts/validate_data.py`，检查仓库当前全部数据、manifest 引用、Fork 图片 URL 和重复 URL。

图片 URL 只进行结构检查，不向网络请求 Fork 文件；`assets/placeholders/` 是现有演示数据的例外。部署工作流也会先执行数据校验，校验成功后才上传 Pages artifact。检查失败时从 Actions 的报错文件和条目序号定位；如果校验器规则与本指南不一致，应一起修改实现、测试和文档。

## 修改前端

- 保持单页、零构建依赖的加载方式；新增 JS/CSS 文件后在 `index.html` 中正确引用。
- 修改页面渲染时使用 `app.js` 既有数据流和 `search.js` 公共接口，不要在卡片渲染中重复实现标签语义。
- 核对桌面与窄屏布局、无结果状态、加载/失败状态和键盘操作。
- 改动视觉样式时参照 `github-design-system-analysis.md`，本地预览真实数据。
- PR 描述用户可见变化；UI 行为变化尽量附截图。

## 提交 PR

保持改动聚焦，说明行为变化和数据迁移方式。新增或修改数据时列出角色、分类、图片来源；修改标签定义时说明旧条目的迁移范围。运行上述两条本地检查，并填写 `.github/pull_request_template.md`。
