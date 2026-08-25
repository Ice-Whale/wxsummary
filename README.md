# wxsummary · 微信群聊日报生成器

把微信每个群聊的消息拉出来，用 AI 自动生成「每天每个群聊有什么新消息」的日总结 / 周报。

- 一键命令：自动导出微信最新数据 → 按群聚合 → AI 逐群总结
- 支持日总结、指定日期、跨日周报，可选「只看原始消息」不调 AI
- 数据与 AI 请求全部本地发起，只有消息文本会发送到你配置的 AI 接口

## 架构

```
chatlog-keeper（微信数据库解密）          wxsummary（本项目）
┌─────────────────────────┐          ┌──────────────────────────┐
│ 解密 + 导出 JSON/HTML    │ ──调用──► │ export_wechat() 封装       │
└─────────────────────────┘          │ 读 wechat_messages.json  │
                                     │ 按日期 + 群聊聚合        │
                                     │ AI（DeepSeek）生成日报   │
                                     └──────────────────────────┘
```

- **解密/导出**：由 chatlog-keeper 完成（一个解密本地微信库、导出成 JSON 的工具）
- **本项目**：一条命令完成「先导出最新数据 → 按群聚合 → AI 总结」

## 🚀 一键配置（macOS，推荐）

一条命令完成：装 chatlog-keeper → 装本项目 → 探测微信 → 提取密钥（active）→ 首次导出 → 生成 `.env`。

```bash
bash install.sh
# 或：./install.sh
```

脚本会自动：

1. 预检 Homebrew / Python3 / git（缺失会提示安装）
2. 克隆并安装 chatlog-keeper
3. 安装本项目 wxsummary
4. `probe` 探测微信状态
5. **提取微信密钥（active 方式）**：
   - 需**先完全退出微信**（菜单「微信」→「退出微信」，等彻底关闭，不要强制退出）
   - 脚本会启动隔离的官方微信客户端自动登录提取，若弹出登录窗口用手机扫码
6. 首次导出最近 7 天聊天记录（需重新打开微信并登录）
7. 引导粘贴 API Key（只写本地 `.env`，不提交、不上传）
8. 生成 `.env`

> 提示：提取密钥后重新打开日常微信即可。脚本不会预置任何第三方 API Key。

## 🪟 一键配置（Windows）

一条命令完成：装 chatlog-keeper → 装本项目 → 探测微信 → 提取密钥（active）→ 首次导出 → 生成 `.env`。

**最简单：双击 `install.bat`**（脚本会自动调用 PowerShell 完成安装）。
也可以在 PowerShell 里手动运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Windows 与 macOS 的区别：

- 不需要 Homebrew：使用 python.org 官方 Python（若未安装，脚本会提示用 `winget` 或官网安装）
- 面向 **PC 版微信 Weixin 4.x**（`Weixin.exe` / `Weixin.dll`），老版 `WeChat.exe` 不支持
- 请以**普通用户**身份运行，**不要「以管理员身份运行」**
- 提示「退出微信」时：在任务栏右下角**托盘图标右键 → 退出微信**（不要用任务管理器强杀）

脚本会自动完成：

1. 预检 PowerShell / Python / git（缺失会提示安装）
2. 克隆并安装 chatlog-keeper
3. 安装本项目 wxsummary
4. `probe` 探测微信状态
5. **提取微信密钥（active 方式）**：需先完全退出微信；脚本会启动隔离的官方客户端，若弹出登录窗口用手机扫码
6. 首次导出最近 7 天聊天记录（需重新打开微信并登录）
7. 引导粘贴 API Key（只写本地 `.env`，不提交、不上传）
8. 生成 `.env`

## 手动配置（备选）

如果你更想手动操作，或需要排查问题，按下面步骤来。

1. 安装 chatlog-keeper：

   ```bash
   git clone https://github.com/labazhou2024/chatlog-keeper.git ~/.chatlog-keeper
   cd ~/.chatlog-keeper && pip install -e .
   ```

2. 提取微信密钥（先完全退出微信，再执行）：

   ```bash
   python -m chatlog_keeper.cli extract-key --source wechat --method active
   ```

3. 安装本项目：

   ```bash
   cd wxsummary
   pip install -e .
   ```

4. 生成配置并填写：

   ```bash
   cp .env.example .env
   # 编辑 .env，填：
   #   EXPORT_JSON=      chatlog-keeper 导出的 JSON 路径（改成你自己的）
   #   EXPORT_DAYS=      生成前自动导出最近多少天（默认 7；设 0 则跳过自动导出）
   #   ZHIPUAI_API_KEY=  你的 API Key（paratera / 智谱等）
   #   AI_API_BASE=      OpenAI 兼容接口地址（默认 https://ai.paratera.com/v1）
   #   ZHIPUAI_MODEL=    模型名（默认 DeepSeek-V4-Flash-0731）
   ```

## 使用

### 生成日报 / 周报（自动导出 + AI 总结）

```bash
wxsummary today                    # 今天的 AI 日报（自动先导出最新数据）
wxsummary yesterday                # 昨天的 AI 日报
wxsummary date 2026-08-22          # 指定日期
wxsummary week --start 2026-08-17 --end 2026-08-23   # 一段时间的 AI 周报
wxsummary week                     # 本周（周一到今天）的 AI 周报
wxsummary today --no-ai            # 不调 AI，只看每个群发了哪些原始消息
wxsummary today --include-direct   # 也包含私聊
wxsummary today -o ~/Desktop/x.md  # 指定输出路径
wxsummary today --force            # 强制重新导出（即使导出文件已是最新）
```

日报输出到 `reports/`：`2026-08-23_report.md`（AI 版）/ `2026-08-23_raw.md`（原始版）。
周报输出到 `reports/`：`2026-08-17_2026-08-23_report.md`。

如果 `wxsummary` 命令未注册，可用 `python -m wxsummary.cli today` 替代。

### 只导出数据，不调 AI

```bash
wxsummary sync --days 7   # 只刷新 wechat_messages.json，不生成日报
wxsummary sync --force    # 强制重新导出（忽略 freshness 判断）
wxsummary info            # 看导出数据统计
```

> 某天没消息？导出范围没覆盖，用 `wxsummary sync --days N` 调大回溯天数。
>
> 默认会「跳过已是当天的导出」：若导出文件的修改时间不早于被查询日期当天零点，就复用旧文件，
> 不重复解密导出，节省时间。需要强制重新导出时加 `--force`。

## 项目结构

```
wxsummary/
├── pyproject.toml      # 依赖（click / python-dotenv / openai）
├── .env.example        # 配置模板（复制为 .env 后填写）
├── reports/            # 日报输出（不进 git）
└── wxsummary/
    ├── __init__.py
    ├── cli.py          # 命令行入口（today/yesterday/date/week/sync/info）
    ├── config.py       # 读 .env 配置（含 EXPORT_DAYS）
    ├── chatlog.py      # 封装 chatlog-keeper 的导出函数
    ├── summary.py      # 读导出 JSON + 按日期/群聚合
    └── ai.py           # AI 日报生成（OpenAI 兼容 SDK，每群一段 + 总览）
```

## 数据格式（chatlog-keeper 导出 JSON）

顶层为消息数组，每条含：`ts`（Unix 秒）、`sender`（昵称）、`sender_wxid`、`chat_room`（群名）、
`conversation_id`、`content`、`msg_type`（1=文字 3=图片 34=语音 43=视频 47=表情
49=文件/链接 10000=系统）、`is_group_chat`、`is_self` 等字段。

## 常见问题

- **某天没消息**：导出范围没覆盖，`wxsummary sync --days N` 调大回溯天数
- **AI 报错**：检查 `.env` 的 `ZHIPUAI_API_KEY` 和 `AI_API_BASE`；先 `--no-ai` 验证数据通路
- **换模型**：`.env` 里改 `ZHIPUAI_MODEL`
- **微信重装/换账号后导不出**：密钥需重新提取，见 chatlog-keeper 的 `extract-key --method active`（先退出微信再跑）

## 隐私说明

- 全部本地离线处理，消息内容只发送到配置的 AI API（paratera/智谱）做总结
- `.env`、`reports/`、`*.json` 数据文件均在 `.gitignore`，密钥与聊天记录不会被提交
