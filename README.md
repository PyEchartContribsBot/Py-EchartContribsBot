# Wiki Chart Bot

用户贡献统计机器人：通过 GitHub Actions 定期执行自动化任务，生成 `echart_option.json` 并更新 MediaWiki 页面内容。
生成的 JSON 可直接作为 [Apache ECharts 5](https://echarts.apache.org/zh/index.html) 的 [setOption](https://echarts.apache.org/zh/api.html#echartsInstance.setOption) 输入，用于渲染图表。


## 文件结构

- `bot.py`：拉取用户贡献并生成 ECharts option JSON
- `upload_to_wiki.py`：登录 MediaWiki 并上传 `echart_option.json`
- `.github/workflows/update-wiki-chart.yml`：定时（或手动）运行，并上传到 Wiki 目标页面

## 目标 MediaWiki 站点上的准备

在开始之前，请务必详阅并遵循目标站点的机器人相关政策（通常在 `Project:Bot` 页面）；若有疑问，请先咨询站点维护人员。

通常这意味着你需要一个持有机器人 `(bot)` 用户组的账号，原因如下：
1. 该项目是长期、定时执行的自动化任务，通常符合申请机器人用户组的场景；
2. 该项目依赖两项机器人用户组相关能力：
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
- `DISPLAY_NAME`
  - 图表中显示的用户名/别名（如需匿名展示可填泛化名称）
- `WIKI_PAGE`
  - 要覆盖写入的页面标题，通常是个人用户页子页面
- `USER_AGENT`
  - 建议配置为：`WikiChartBot/1.0 (https://github.com/<your‑org>/<your‑仓库>; <your-noreply-email>) requests/2.x`  
    - 即在括号中填写你的 GitHub 仓库 URL 和可联系邮箱。
  - 若包含邮箱/联系信息，建议放 secret
- `BOT_USERNAME`
  - Bot 的登录名
  - 建议使用 BotPassword 登录名（常见格式：`主账号名@Bot密码名`），[BotPasswords](https://www.mediawiki.org/wiki/Manual:Bot_passwords/zh) 可限制机器人权限和可编辑范围；若站点支持，建议在 `Special:BotPassword` 创建后用于登录
  - 此项目当前不支持 OAuth（原作者目标 wiki 站点不支持）
- `BOT_PASSWORD`
  - Bot 登录密码

### Variables

- `WIKI_API`
  - 例如：`https://meta.wikimedia.org/w/api.php`
  - 用于抓取 usercontribs 和上传内容
- `EXCLUDED_NAMESPACES`
  - 可选，逗号分隔整数，例如：`1,2,3,5,7,9,11,13,15,275,711,829`
  - 用于排除不统计的命名空间
  - 不设置时使用默认排除列表，排除“用户”和数个常用的讨论命名空间
  - 如果调整，请确保 `bot.py` 中构建 JSON 的 subtext 与排除列表一致
- `EDIT_TAG_CANDIDATES`
  - 可选，逗号分隔标签候选列表，按顺序尝试，例如：`Bot,Automation tool`
  - 默认值：`Bot,Automation tool`
  - 留空时不尝试任何 `tags`，仅执行无标签编辑

> Workflow 兼容策略：`WIKI_USER` / `DISPLAY_NAME` / `USER_AGENT` / `WIKI_PAGE` 均为 **Secrets 优先，并支持 Variables**，可按实际情况选择。

> 仓库可见性提示：将仓库设为 Public 通常可减少（或避免）GitHub Actions Minutes 的消耗；具体以 GitHub 当前计费政策为准。

## bot.py 配置（可选）

推荐通过环境变量配置，无需修改 `bot.py` 源码：

- `EXCLUDED_NAMESPACES`：排除命名空间（逗号分隔整数）
- `USER_AGENT`：建议通过环境变量配置（**重要！**）
- `DISPLAY_NAME`：未设置或为空时，默认回退为 `WIKI_USER`

**注意：**
- `API_URL` 和 `USER` 从环境变量读取，在 Actions 中会自动使用 Secrets/Variables 配置
- `EXCLUDED_NAMESPACES` 也支持从 Variables/.env 读取（逗号分隔整数）
- `USER_AGENT` 也可通过 Variables 统一配置（`vars.USER_AGENT`）
- 建议设置有意义的 `User-Agent`（包含项目标识与联系方式）

## Workflow 行为

- 每天 UTC `03:00` 自动运行
- 支持手动触发（`workflow_dispatch`）
- 使用 Python `3.11`
- 安装依赖：`requests`
- 先运行 `bot.py` 生成 `echart_option.json`
- 再运行 `upload_to_wiki.py`，按 MediaWiki 标准流程上传：
  1. 获取 login token
  2. 登录
  3. 查询当前登录用户组（`meta=userinfo&uiprop=groups`）
  4. 获取 csrf token
  5. 优先使用 `action=edit` 的 `bot=1` 标记覆盖页面内容
    - 若 `BOT_USERNAME` 不具备 `(bot)` 用户组，workflow 会先给出警告并继续执行；带 bot 标记失败时会自动回退为普通编辑
     - 这表示当前账号并非机器人账号，长期持续自动编辑可能违反站点策略并导致被封禁
    - 变更标签由 `EDIT_TAG_CANDIDATES` 控制（默认：`Bot,Automation tool`），会按顺序尝试；若站点不支持会自动回退为不带标签
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
- `bot.py` 支持在拉取贡献前自动登录：
  - 读取 `BOT_USERNAME` 与 `BOT_PASSWORD`（Secrets）
  - 成功登录后再执行 `usercontribs` 查询

## 本地运行（.env）

- `bot.py` 会自动读取项目根目录下的 `.env`
- 可先复制 `.env.example` 为 `.env`，再填入你的真实值
- `.env` 已在 `.gitignore` 中忽略，不会被提交

示例：

```bash
cp .env.example .env
python bot.py
# 如需在本地直接上传到 Wiki，再执行：
python upload_to_wiki.py
```

本地执行 `upload_to_wiki.py` 时，请确保 `.env` 或系统环境中已设置 `WIKI_API`、`WIKI_PAGE`、`BOT_USERNAME`、`BOT_PASSWORD`；可选设置 `EDIT_TAG_CANDIDATES`。

## 首次验证建议

1. 提交并推送代码到 GitHub
2. 打开 Actions -> `Update Wiki Chart`
3. 点击 **Run workflow** 手动执行一次
4. 检查日志中是否出现：`Wiki page updated successfully.` 或 `No content changes detected; skip edit.`

## 安全说明

- **所有敏感信息**（真实用户名、密码）均使用 GitHub Secrets 存储
- `DISPLAY_NAME` 与 `WIKI_PAGE` 在需要匿名时建议使用 Secrets（而非普通仓库变量）
- 仓库设为 Public 时，代码中不会暴露 Secrets（前提是敏感信息仅存放于 Secrets）
- GitHub Actions 会自动在日志中隐藏（mask）secrets 的值
- 本地运行时请确保 `.env` 文件安全，不要提交到版本控制系统

## 声明

本项目使用了 GitHub Copilot。