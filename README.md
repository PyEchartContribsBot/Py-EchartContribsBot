# Wiki Chart Bot

自动化用户贡献统计脚本：通过 GitHub Actions 定期执行自动化任务，生成符合 [Apache ECharts 5](https://echarts.apache.org/zh/index.html) 的 [setOption](https://echarts.apache.org/zh/api.html#echartsInstance.setOption) 输入要求的 JSON ，并更新 MediaWiki 页面内容。

## 文件结构

- `generate_chart_json.py`：使用 usercontribs 拉取用户贡献并生成 ECharts option JSON
- `publish_chart_json.py`：使用 edit 上传生成的 JSON 到指定 MediaWiki 页面
- `.github/workflows/update-wiki-chart.yml`：定时（或手动）运行 generate_chart_json.py 和 publish_chart_json.py 的 GitHub Actions Workflow
- `.env.example`：本地运行时的环境变量示例文件

## 安全说明

此项目**推荐** ≥ 1.27 的 MediaWiki 版本使用。这是因为此项目使用 login 登录，较低版本可能需要直接使用主账户登录，这会带来安全风险。
- 根据MediaWiki API文档 [[Special:Apihelp/login]]：`此操作只应与[[Special:BotPasswords]]一起使用；用于主账户登录的方式已弃用，并可能在没有警告的情况下失败。要安全登录主账户，请使用action=clientlogin。`
- [BotPasswords](https://www.mediawiki.org/wiki/Manual:Bot_passwords/zh)（MediaWiki 版本 ≥ 1.27）可限制机器人权限（包含可编辑范围）；若站点支持，建议在[[Special:BotPasswords]]创建后用于登录

此项目使用 Secrets 处理敏感信息，所有敏感信息都应当使用 Secrets 储存。请不要将敏感信息直接放在代码或公开的仓库 Variables 中，尤其是当仓库设为 Public 时。GitHub Actions 会自动在日志中隐藏（mask）secrets 的值

仓库设为 Public 时，代码中不会暴露 Secrets（前提是敏感信息仅存放于 Secrets）

在本地使用 `.env` 文件存储敏感信息时，请确保不被提交，其应当已在 `.gitignore` 中忽略。

## 目标 MediaWiki 站点上的准备

在开始之前，请务必详阅并遵循目标站点的机器人相关政策（通常在 `Project:Bot` 页面）；若有疑问，请先咨询站点维护人员。

通常这意味着你需要一个持有机器人 `(bot)` 用户组的账号，原因如下：
1. 此项目是长期、定时执行的自动化任务，通常符合申请机器人用户组的场景；
2. 此项目依赖两项机器人用户组相关能力：
  - 在 API 查询中使用更高上限 `(apihighlimits)`
  - 被识别为自动化过程 `(bot)`
3. 若长期以非机器人身份执行自动化操作，可能导致账号被封禁。

该账号应当是专用账号，因为：
1. 机器人发生意料之外的行为导致负面后果时，可能会被站点管理员急停（临时封禁）；
2. 多数站点通常不允许机器人在普通账号上运行，并可能有其他要求。

## GitHub 上的配置

在 GitHub 仓库中配置以下项目：

### Secrets

- `WIKI_USER`
  - 要统计贡献的用户名

    可带`User:`前缀，但任何别名（如`U:`）都不支持；建议不加
    - 根据 MediaWiki API 文档[[Special:ApiHelp/query]]，支持 `用户名、​IP、​临时用户和​跨wiki用户名（例如“前缀>示例用户”）`（“跨wiki用户名”指跨维基导入的页面修订历史中被导入的用户名，并非允许[[Special:Interwiki]]的跨Wiki链接）
  - 如需查询多用户：使用 `|` 或 `%7C`（管道符）分隔多个用户名，例如 `User1|User2|User3`
    - 图表会自动合并多个用户的贡献数据，目前不支持拆分
    - `DISPLAY_NAME` 会默认使用 `WIKI_USER` 中的第一个用户名作为显示名称
- `DISPLAY_NAME`
  - 图表中显示的用户名/别名
  - 未设置或为空时，自动从 `WIKI_USER` 提取第一个用户作为默认值（若 `WIKI_USER` 包含多个用户，则只使用第一个）
- `WIKI_PAGE`
  - 要覆盖写入的页面标题，通常是个人用户子页面
  - 需为完整页面名称，例如：`User:ExampleBot/ContributionChart`
- `USER_AGENT`
  - 建议配置为：`WikiChartBot/1.0 (https://github.com/<your‑org>/<your‑仓库>; <your-noreply-email>) requests/2.x`  
    - 即在括号中填写你的 GitHub 仓库 URL 和可联系邮箱。
  - 若包含私人邮箱/联系信息，建议放 secret
- `BOT_USERNAME`
  - Bot 的登录名
  - BotPasswords的机器人名称格式：`主账户@机器人名称`
  - 此项目当前不支持 OAuth（原作者目标 wiki 站点未安装 OAuth 扩展）
- `BOT_PASSWORD`
  - Bot 登录密码

### Variables

- `WIKI_API`
  - 例如：`https://meta.wikimedia.org/w/api.php`
  - 用于抓取 usercontribs 和上传内容
- `EXCLUDED_NAMESPACES`
  - 可选，逗号分隔整数，例如：`1,2,3,5,7,9`
  - 用于排除不统计的命名空间
  - 不设置时会根据返回贡献自动排除：`ns=2`(用户) 与所有奇数命名空间（讨论页）
- `NAMESPACE_MODE`
  - 可选，`top` 或 `all`
  - 默认 `top`：仅展示 Top N 命名空间，其余合并为 `其他命名空间`
  - `all`：展示全部命名空间
- `TOP_NAMESPACE_LIMIT`
  - 可选，正整数，默认 `10`
  - 仅在 `NAMESPACE_MODE=top` 时生效
- `CHART_STYLE`
  - 可选，`namespace_stacked` 或 `monthly_total`
  - 默认 `namespace_stacked`：按命名空间堆叠
  - `monthly_total`：按月总贡献（单序列）
- `CHART_SERIES_TYPE`
  - 可选，`bar` 或 `line`
  - 默认 `bar`：直方图
  - `line`：折线图（堆叠样式下会带面积填充）
- `EDIT_TAG_CANDIDATES`
  - 可选，逗号分隔标签候选列表，按顺序尝试，例如：`bot, Bot`
  - 默认值：`bot, Bot`
  - 留空时不尝试任何 `tags`，仅执行无标签编辑

> Workflow 兼容策略：`WIKI_USER` / `DISPLAY_NAME` / `USER_AGENT` / `WIKI_PAGE` 均为 **Secrets 优先，并支持 Variables**，可按实际情况选择。

> 仓库可见性提示：将仓库设为 Public 通常可减少（或避免）GitHub Actions Minutes 的消耗；具体以 GitHub 当前计费政策为准。

## generate_chart_json.py 配置（可选）

推荐通过环境变量配置，无需修改 `generate_chart_json.py` 源码：

- `EXCLUDED_NAMESPACES`：排除命名空间（逗号分隔整数；留空时自动排除 `ns=2`(用户) 与奇数命名空间（讨论页））
- `CHART_STYLE`：图表方案（`namespace_stacked` 或 `monthly_total`，默认 `namespace_stacked`）
- `NAMESPACE_MODE`：命名空间序列展示策略（`top` 或 `all`）
- `TOP_NAMESPACE_LIMIT`：Top 命名空间数量（正整数，默认 `10`）
- `CHART_SERIES_TYPE`：图表系列类型（`bar` 或 `line`，默认 `bar`）
- `USER_AGENT`：建议通过环境变量配置（**重要！**）
- `DISPLAY_NAME`：未设置或为空时，自动从 `WIKI_USER` 提取第一个用户名作为默认值
  - 若 `WIKI_USER` 包含多个用户（以 `|` 或 `%7C` 分隔），只使用第一个用户作为 `DISPLAY_NAME`

**注意：**
- 以上变量均通过环境变量读取，在 Actions 中配置对应 Secrets/Variables 即可
- `USER_AGENT` 可通过 `vars.USER_AGENT` 统一配置；若含私人联系信息，建议改放 Secrets
- 建议设置有意义的 `User-Agent`（包含项目标识与联系方式）

## 图表行为

- `CHART_STYLE=namespace_stacked`（默认）
  - 输出按月命名空间堆叠图（默认 `bar`，可切 `line`）
  - 每个系列默认使用 `{{ns:命名空间数字}}` 作为名称，便于 wiki 侧解析本地化命名空间名
  - 当命名空间较多时，默认启用 `Top N + Other`，降低 legend 拥挤风险
- `CHART_STYLE=monthly_total`
  - 输出按月总贡献图（单序列，默认 `bar`，可切 `line`）

## Workflow 行为

- 每天 UTC `03:00` 自动运行
> [!NOTE]
> 可根据需要调整 cron 表达式；
> 
> 在公共仓库中，如果60天内没有任何仓库活动，则使用 `schedule` 事件定时的 workflow 将被自动禁用；
> 
> `schedule` 表达式语法及更多信息见：[GitHub文档：触发工作流的事件](https://docs.github.com/zh/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- 支持手动触发（`workflow_dispatch`）
- 使用 Python `3.11`
- 安装依赖：`requests`
- 先运行 `generate_chart_json.py` 生成 `echart_option.json`
- 再运行 `publish_chart_json.py`，按 MediaWiki 标准流程上传：
  1. 获取 login token
  2. 登录
  3. 查询当前登录用户组（`meta=userinfo&uiprop=groups`）
    - 若 `BOT_USERNAME` 不具备 `(bot)` 用户组，workflow 会先给出警告并继续执行
    - 这表示当前账号并非机器人账号，长期持续自动编辑可能违反站点策略并导致被封禁
  4. 获取 csrf token
  5. 优先使用 `action=edit` 的 `bot=1` 标记覆盖页面内容
    - 即使上一步确认当前账号不具备 `(bot)` 用户组，也仍会统一先尝试 `bot=1`
    - 若目标站点明确拒绝带 bot 标记的编辑，workflow 会自动回退为普通编辑
    - 通常 MediaWiki 站点即使账号缺少 `(bot)` 用户组，也不会因 `bot=1` 直接报错，仅会不应用该标记
    - 变更标签由 `EDIT_TAG_CANDIDATES` 控制（默认：`bot, Bot`），会按顺序尝试；若站点不支持会自动回退为不带标签
- 如果页面内容未变化，自动跳过编辑
- 失败时输出错误信息

## API 使用规范

此项目遵循 [MediaWiki API 礼仪](https://www.mediawiki.org/wiki/API:Etiquette)：

✅ **已实现的最佳实践：**
- 设置有意义的 User-Agent（包含项目信息和联系方式）
- 使用 gzip 压缩减少带宽
- 串行请求（等待一个请求完成后再发送下一个）
- 使用 `maxlag` 参数避免在服务器高负载时运行
- 使用 `uclimit=max` 和 continue 机制处理分页

## 受限站点说明

- 部分站点会限制匿名 API 读取（会返回 `action-notallowed` / `Unauthorized API call`）
- `generate_chart_json.py` 支持在拉取贡献前自动登录：
  - 读取 `BOT_USERNAME` 与 `BOT_PASSWORD`（Secrets）
  - 成功登录后再执行 `usercontribs` 查询

## 本地运行（.env）

- `generate_chart_json.py` 和 `publish_chart_json.py` 会自动读取项目根目录下的 `.env`
- 可先复制 `.env.example` 为 `.env`，再填入你的真实值
- `.env` 已在 `.gitignore` 中忽略，不会被提交
- 切记不要包含敏感信息的 `.env` 提交到版本控制系统，尤其是公开仓库

示例：

```bash
cp .env.example .env
python generate_chart_json.py
# 如需在本地直接上传到 Wiki，再执行：
python publish_chart_json.py
```

本地执行 `publish_chart_json.py` 时，请确保 `.env` 或系统环境中已设置 `WIKI_API`、`WIKI_PAGE`、`BOT_USERNAME`、`BOT_PASSWORD`；可选设置 `EDIT_TAG_CANDIDATES`。

说明：`generate_chart_json.py` 与 `publish_chart_json.py` 均读取 `WIKI_API`。

## 首次验证建议

1. 提交并推送代码到 GitHub
2. 打开 Actions -> `Update Wiki Chart`
3. 点击 **Run workflow** 手动执行一次
4. 检查日志中是否出现：`Wiki page updated successfully.` 或 `No content changes detected; skip edit.`

## 声明

此项目使用了 GitHub Copilot。
