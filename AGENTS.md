# AGENTS.md

## 项目目标

奶-hub 有两个同等重要的目标：维护一个由社区贡献者的公开 Fork 提供图片、由主仓库数据记录汇总展示的分布式表情包站；以及让 GitHub 新手能够通过一次真实投稿学会 Fork、分支、commit 和 Pull Request。文档、校验规则和工作流应同时服务这两个目标。

## 协作边界

- 开始工作前阅读 [README.md](README.md)、[CONTRIBUTING.md](CONTRIBUTING.md) 和当前任务对应的 `docs/` 指南。
- 网站是零构建静态站点。未经明确需要，不要引入前端框架、包管理器、构建步骤或运行时依赖。
- 角色、分类和表情由 `data/` 驱动；不要为了新增角色或分类而在 `assets/js/app.js` 或 `index.html` 写死数据。
- 低门槛表情投稿走共享 Issue 评论区；网站/项目建议与问题反馈走普通 Issue；GitHub 新手通过 Fork、工作分支和 JSON PR 投稿；项目代码改动保持范围聚焦。
- 社区图片放在贡献者自己的公开 Fork 的 `image` 分支。不要把该分支合并进主仓库，也不要建议贡献者删除或私有化承载本站图片的 Fork。
- 修订既有数据时优先修改原条目；不得丢失已记录的来源信息。相同 URL 不重复新增。
- 图片若被版权所有者指出存在问题，删除主仓库对应图片链接，并通知承载图片的 Fork 所有者处理。
- 不在数据、文档、日志或 workflow 中加入密码、访问令牌或其他凭据。

## 术语

- **角色（role）**：`data/manifest.json` 中的一项，例如 `naiwa`（奶蛙）；其 `id` 对应 `data/<role-id>/` 目录。
- **分类（category）**：角色下的一种内容类型，由 manifest 的 `subcategories` 项描述，含分类 ID、名称和数据文件路径。
- **分类文件（category file）**：`animated.json` 或 `static.json` 的统称；每个分类文件是表情条目数组。
- **表情条目（meme entry）**：分类文件中的一个对象，包含 `title`、`url` 和 `tags`。
- **标签维度（tag dimension）**：`tags.json` 的一个顶层键，例如 `smile`、`age limit`、`artistic merit`。
- **维度内标签序号（local tag index）**：某一标签维度对象中的数字键，例如 `smile` 下的 `"2"` 表示该维度的“大笑”。序号只在所属维度内有意义。
- **标签数组位置（tag array position）**：表情条目 `tags` 数组中的位置；从 0 开始，依次对应 `tags.json` 顶层维度的书写顺序。 
- **本地 Fork 图片 URL**：贡献者公开 Fork 内 `NaiLoong/blob/image/<path>` 的 GitHub 文件地址。该 URL 作为站点图片来源；Fork 必须持续公开和保留。
- **占位资源**：`assets/placeholders/` 下随主仓库维护的演示和 fallback 图片，不是社区投稿的外部图片来源。

## 目录职责

- `index.html`：网站主页面骨架、导航和文案。
- `assets/css/`：设计参考 `github-design-system-analysis.md`。
- `assets/js/app.js`：加载 manifest 和数据，渲染页面、路由和交互。
- `assets/js/search.js`：标签定义解析、搜索和筛选语义。
- `assets/js/ghimg.js`：GitHub 图片链接转换、代理探测和失败回退。
- `assets/placeholders/`：仓库自带的占位和兜底图片。
- `data/manifest.json`：角色和分类目录。
- `data/<role-id>/`：该角色的分类文件及 `tags.json`。
- `.github/ISSUE_TEMPLATE/`：网站或项目建议、问题反馈模板及共享投稿 Issue 入口。
- `.github/workflows/`：PR 测试/数据校验和 GitHub Pages 部署。
- `scripts/validate_data.py`：数据契约、标签语义、图片 URL 格式和重复 URL 校验。
- `tests/`：数据校验器和标签解析测试；Python 测试使用标准库，搜索测试使用 Node 内置断言，不引入第三方依赖。
- `docs/`：按参与方式区分的贡献指南。
- `CONTRIBUTING.md`：三类参与者的文档导航。

## 数据契约

- `data/manifest.json` 是非空数组。每个角色含唯一、非空 `id` 和非空 `name`，至少有一个分类。角色和分类 ID 使用小写英文、数字及连字符；角色目录名与角色 ID 相同。
- `subcategories[].file` 是相对 `data/` 的 `.json` 分类文件路径，必须位于对应角色目录下。分类 ID 在同一角色内唯一，分类名称非空。
- 每个分类文件是 JSON 数组；数组中每一项是对象，包含非空 `title`、非空 `url` 和 `tags`。
- `tags.json` 是有序 JSON 对象。顶层键为标签维度，维度值是“维度内标签序号 → 标签文字”的对象。维度书写顺序决定 `tags` 数组位置；维度内部的整数序号不做跨维度展平。
- `tags` 数组必须恰有一个元素对应每个标签维度，按维度顺序填写非负本地整数序号；未知维度使用 JSON `null`。例如 `[2, null, 0]` 表示第一维取本地序号 2、第二维未知、第三维取本地序号 0。
- `tags` 也允许对象写法 `{ "维度名": 本地整数序号或标签文字或 null }`，适合强调维度名或只记录部分维度。未知维度名和未定义的序号/标签文字均无效。
- 当前项目的常规分类为 `animated`（动图）和 `static`（静态图）；数据结构不在校验器中硬编码只允许这两个分类。极短视频应转换成 GIF；较长视频不收录。
- 新投稿 `url` 必须指向贡献者公开 Fork 中 `NaiLoong/blob/image/<path>` 的 GitHub URL。禁止其他图床 URL。校验器只校验 URL 结构，不联网请求图片；本地 `assets/placeholders/` 下已存在的占位资源例外保留。
- 校验器拒绝数据集中重复的图片 URL。图片内容是否重复由人工审核判断。
- 单张投稿图片严格小于或等于 5 MB；鼓励压到 2 MB 以下。PR 校验不下载 Fork 图片，不能据此判断远程文件体积。
- 修改维度顺序或已有维度内标签序号时，同步核查并迁移受影响条目。数组标签从来不表示展平序号；不得重新引入展平解释。
- 修改数据规则时同步更新校验器、测试、README 数据规范和相关贡献指南。

## 校验与开发

在仓库根目录运行：

```bash
python scripts/validate_data.py
python -m unittest discover -s tests -v
node tests/search.test.js
python -m http.server 8080
```

前两条是 PR CI 和部署前检查；第三条用于浏览器预览，访问 `http://localhost:8080`。校验器和测试仅依赖 Python 标准库，不请求网络。

修改校验规则时增加有效和无效输入测试。修改标签解析时，测试本地序号、`null`、对象写法、筛选和展示；修改图片规则时测试 image 分支结构、错误分支、重复 URL，且不以真实网络可用性为测试条件。用户可见 UI 改动在本地预览。

## 工作流约定

- `.github/workflows/pr-check.yml` 在所有 Pull Request 上执行校验器单元测试和全仓库数据检查。
- `.github/workflows/deploy.yml` 仅在 `main` 更新或手动触发；测试和数据校验成功后才部署 GitHub Pages。
- PR 图片 URL 不做联网探测；只检查 Fork URL 结构和仓库内重复 URL。主仓库的占位资源例外。
- 手动部署不能绕过检查。面向 fork PR 的 job 不得获得部署凭据。
- 检查失败应修复数据、代码或测试，不要缩小触发范围、跳过失败步骤或接受违背数据契约的格式。

## 文档约定

- 对贡献者的说明只包含可直接执行的流程、规则和必要背景，不记录维护者之间的讨论过程、内部决策对话或未完成的实现计划。
- 新手指南直接写 Git 命令、命令作用和操作顺序，不用外部教程链接代替流程。
- 低门槛投稿、GitHub 新手 PR、项目代码贡献是三个独立入口，互相链接但不混成一个流程。
- 命令示例应可按顺序执行，标明哪些名称要替换；不要建议 `--force`、`reset --hard` 作为日常修复方式。
- 截图占位使用明确说明截图主题的引用块，便于维护者补图和复核。
- `LICENSE` 的 MIT 许可不代表社区图片自动采用 MIT 许可。

## 待维护者确认

以下规则仍需维护者以后明确或操作；不影响当前指南按已确定约定执行。

1. **共享投稿 Issue 尚未创建。** 维护者需新建普通 Issue，标题使用「奶-hub 表情包投稿区」，添加 `submission` 标签并置顶；随后将 `.github/ISSUE_TEMPLATE/config.yml` 和站点投稿入口更新为该 Issue 的固定 URL。创建步骤在仓库外直接告知维护者，不把该操作说明写进投稿人指南。
2. **归档方案尚未落地。** 维护者计划定期归档图片；频率、归档范围、校验和、恢复流程及外部服务是否允许这些图片仍待定义。归档落地前，贡献者 Fork 必须保持公开且不删除。
3. **授权反馈的处置范围。** 目前确定的操作是移除主仓库对应 URL 并通知 Fork 所有者处理；通知渠道、响应时限、争议处理和作者署名格式尚未规定。Issue 模板只需用一句话告知此处理方式。
4. **5 MB 限制执行范围。** 文档把 5 MB 作为严格上限，但 PR 校验不会下载 Fork 图片，因此暂由投稿人和人工审核执行。若将来要求机器执行，须评估安全、网络依赖、超时和外部 GitHub 限流后再设计。
5. **标签质量的人工处理流程。** CI 验证标签维度和本地值有效；标签是否合适由 PR 贡献者拟定并由维护者审核。错误时可请求贡献者修改，或经审核直接编辑 PR 分支；低门槛 Issue 投稿者不负责填写数字标签。
6. **远程图片失效治理。** 校验器不联网检查 Fork 文件是否仍存在。贡献者删除或私有化 Fork 会导致资源失效；定期归档计划的监测和恢复责任尚待确定。
7. **GitHub UI 教程维护。** Fork、分支创建、文件上传和 PR 界面可能变化；由维护者定期检查文字和截图是否仍与当前 GitHub 界面一致。
