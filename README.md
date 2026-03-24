# 🎬 JavSpider Stack

<div align="center">

**本地优先的 JavBus 数据管家 — 封面永不失效、磁力永不断链**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()

</div>

> **English summary:** JavBus metadata manager with local-first design — covers and avatars cached locally so they never get blocked or expired. Async crawler, SQLite storage, WebSocket real-time progress, magnet auto-pick (UC/4K/subtitle priority), and a clean built-in WebUI. One-command startup on macOS / Linux / Windows.

---

> ⚠️ **免责声明 / Disclaimer**
>
> 本项目仅供技术学习与个人研究使用。使用前请确认遵守所在地区的相关法律法规，并尊重目标网站的服务条款。
> 本工具不存储、不传播任何受版权保护的媒体内容，数据库仅在本地使用，不得用于商业用途。
> 作者不对任何滥用行为承担责任。
>
> *This project is for educational and personal research purposes only. Please comply with local laws and the target website's terms of service. The author assumes no responsibility for any misuse.*

---
<img width="2974" height="1500" alt="d95d48d8296dbe57d67e9ac98bcf59e8" src="https://github.com/user-attachments/assets/7abe8ba3-6c15-419c-9c75-ae44e76fe9e0" />
<img width="2976" height="1332" alt="d5e1202a9e91ea65b4cca20e1a1c047c" src="https://github.com/user-attachments/assets/791bb71a-ece6-4094-9137-ef744683c4e6" />
<img width="2996" height="1046" alt="ee1867d81442efd01680e2f09c7b501f" src="https://github.com/user-attachments/assets/b42cd8e2-0339-4fd2-8e39-ffd40e20336e" />
<img width="3006" height="942" alt="396d19b9ec6f265b302b5de303778dfc" src="https://github.com/user-attachments/assets/9b1c62b6-094a-419a-bdc7-d711368b0148" />




## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🎬 **作品管理** | 爬取、存储、搜索作品信息，按番号 / 日期 / 女优多维筛选 |
| 👩 **女优档案** | 批量爬取女优列表与详细信息，头像本地化存储 |
| 🔗 **磁力优选** | 自动筛选最优磁力（支持 UC / 4K / 字幕优先级排序）|
| 🖼️ **封面本地化** | 自动下载封面到本地，彻底摆脱被墙的外部图片服务器 |
| 📡 **实时进度** | WebSocket 实时推送爬取进度，进度条可视化 |
| 🎯 **在线直达** | 作品详情一键跳转 MissAV / Jable 在线视频 |
| 🔍 **图片预览** | 封面点击放大查看高清原图 |
| 🛡️ **防屏蔽机制** | UA 轮换、请求限速、指数退避重试、代理支持 |
| 🌍 **跨平台** | 支持 macOS / Linux / Windows（WSL 或 start.py）|

---

## 💡 为什么选择 JavSpider Stack？

| 痛点 | JavBus 在线浏览 | JavSpider Stack |
|------|----------------|----------------|
| 封面图片被墙 | ❌ 403 无法显示 | ✅ 本地缓存，永不断线 |
| 女优头像加载失败 | ❌ 依赖外站图片 | ✅ 下载到本地，秒开 |
| 磁力链接断链 | ❌ 需要每次搜索 | ✅ 存本地数据库，随时查 |
| 爬取进度不透明 | ❌ 不知道跑到哪了 | ✅ WebSocket 实时推送 |
| 网络不稳定中断 | ❌ 需要重新来过 | ✅ 断点续爬，自动重试 |



## 🚀 快速开始

### 环境要求

- **Python 3.11 或 3.12**（推荐）
- macOS / Linux / Windows（WSL）
- 可访问目标网站的网络环境（如需代理，见下文）

### 一键启动

**macOS / Linux**
```bash
git clone https://github.com/hk-raints/javspider_stack.git
cd javspider_stack
./start.sh
```

**Windows**
```bash
git clone https://github.com/hk-raints/javspider_stack.git
cd javspider_stack
python start.py
```

启动后访问：**http://localhost:8088**

`start.sh` 会自动完成：
1. ✅ 检查 Python 版本
2. ✅ 创建虚拟环境
3. ✅ 安装依赖
4. ✅ 初始化数据库
5. ✅ 启动服务并显示访问地址

### 手动启动

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8088
```

### 代理配置（可选）

```bash
# 如果目标网站在你的网络下无法直连
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
./start.sh
```

---

## 📖 使用流程

### 首次使用完整步骤（按顺序执行）

```
第1步：启动服务  →  第2步：爬取女优列表  →  第3步：爬取作品  →  第4步：（可选）下载封面
```

**第 1 步：启动服务**
```bash
./start.sh
```
浏览器访问 **http://localhost:8088**，看到界面说明启动成功。

**第 2 步：爬取女优列表**
- 在页面左侧或顶部找到「**爬取女优列表**」按钮
- 点击后等待完成（女优数量越多耗时越长，可配置请求间隔减少被封概率）

**第 3 步：爬取作品**
- 从女优下拉框选择一个或多个女优
- 点击「**开始爬取**」，自动获取所有作品与磁力链接
- 爬取进度实时显示在页面

**第 4 步（可选）：下载封面到本地**
```bash
# 关闭服务后，在项目目录执行
python scripts/download_covers.py        # 下载作品封面（约 5~10 分钟）
python scripts/download_all_actress_avatars.py  # 下载女优头像（约 30 分钟）
```
封面本地化后，图片加载不再依赖外部服务器。

---

### 日常使用流程

```
启动服务  →  选择女优  →  爬取新作品  →  浏览 / 观看
```

1. **启动服务** — `./start.sh`（已有数据时跳过第 2 步）
2. **获取女优列表** — 首次使用需要爬取一次，后续数据保留在本地
3. **爬取作品** — 选择女优，点击"开始爬取"
4. **浏览与观看** — 作品列表支持多维筛选；点击封面放大；详情页跳转 MissAV / Jable

---

## 🏗️ 项目结构

```
javspider_stack/
├── api/                        # FastAPI 路由与接口层
│   └── main.py                 # 主入口，所有 REST API
├── core/                       # 核心爬虫模块
│   ├── anti_block.py           # 防屏蔽（UA轮换、代理池、退避策略）
│   ├── http_client.py          # 异步 HTTP 客户端封装
│   ├── pipeline_manager.py     # 四阶段爬取流水线
│   └── parsers/                # HTML 解析器
├── db/                         # 数据库层
│   ├── models.py               # SQLAlchemy 数据模型
│   └── session.py              # 数据库会话管理
├── services/                   # 业务逻辑层
│   ├── crawler_service.py      # 爬虫调度服务
│   ├── enhanced_crawl.py       # 增强爬取逻辑
│   └── task_queue.py           # 异步任务队列
├── scripts/                    # 独立工具脚本
│   ├── download_covers.py              # 批量下载封面图
│   ├── download_all_actress_avatars.py # 批量下载女优头像
│   ├── download_actress_avatars.py     # 下载单个女优头像
│   └── download_missing_covers.py      # 补充下载缺失封面
├── dashboard/                  # 前端单页应用
│   └── index.html              # 主页看板（WebUI）
├── static/                     # 静态资源（图片运行时生成，不含于仓库）
│   ├── covers/                 # 作品封面（本地化存储）
│   ├── avatars/                # 女优头像（本地化存储）
│   ├── style.css               # 样式
│   ├── app.js                  # 前端逻辑
│   └── progress.css            # 进度条样式
├── data/                       # 数据库文件（运行时生成，不含于仓库）
├── docs/                       # 文档资源（如赞赏码）
├── config.py                   # 全局配置
├── requirements.txt            # Python 依赖
├── start.sh                    # macOS/Linux 一键启动脚本
├── start.py                    # Windows 一键启动脚本
└── websocket_manager.py        # WebSocket 连接管理
```

---

## ⚙️ 配置说明

编辑 `config.py` 调整运行参数：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `REQUEST_DELAY_MIN` | 3.0 秒 | 请求最小间隔（礼貌爬取）|
| `REQUEST_DELAY_MAX` | 8.0 秒 | 请求最大间隔 |
| `MAX_RETRIES` | 5 | 请求最大重试次数 |
| `SERVER_PORT` | 8088 | Web 服务端口 |
| `PROXY` | 空 | 代理地址（优先读环境变量）|

---

## 🛠️ 技术栈

| 层次 | 技术选型 |
|------|---------|
| **后端框架** | Python 3.11+ / FastAPI / SQLAlchemy |
| **数据库** | SQLite（零配置，开箱即用）|
| **爬虫** | httpx（异步）+ BeautifulSoup4 |
| **前端** | 原生 HTML / CSS / JavaScript（无构建工具）|
| **实时通信** | WebSocket |

---

## 📦 数据存储说明

| 目录/文件 | 说明 | 是否提交 Git |
|----------|------|-------------|
| `data/javbus.db` | SQLite 数据库，含全部作品/女优数据 | ❌ 不提交 |
| `static/covers/` | 作品封面图片（批量下载后生成）| ❌ 不提交 |
| `static/avatars/` | 女优头像图片（批量下载后生成）| ❌ 不提交 |

> 以上目录结构已通过 `.gitkeep` 文件保留，clone 后目录即存在，无需手动创建。

---

## ❓ 常见问题

**Q: 爬取时提示 403 / 连接超时？**
A: 配置代理即可解决，见 [代理配置](#代理配置可选) 章节。

**Q: 封面图片无法显示？**
A: 运行 `python scripts/download_covers.py` 批量下载封面到本地。

**Q: Windows 下 `start.sh` 无法执行？**
A: 直接运行 `python start.py` 即可，Windows 版本脚本已包含所有功能。

**Q: 数据库在哪里？**
A: `data/javbus.db`，SQLite 格式，可用 [DB Browser for SQLite](https://sqlitebrowser.org/) 直接查看。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

- 🐛 **Bug Report**：请在 Issues 中描述复现步骤
- 💡 **功能建议**：欢迎在 Issues 讨论
- 🔧 **代码贡献**：Fork → 新建分支 → 提交 PR

---

## ☕ 支持作者

如果这个项目对你有帮助，欢迎请作者喝杯咖啡 ☕

<div align="center">

<img src="docs/wechat_pay.jpg" width="280" alt="微信赞赏码 - Raints">

**微信扫码赞赏**

*你的支持是持续维护的动力 🙏*

</div>

---

## 📄 License

[MIT](LICENSE) © Raints

---

<div align="center">
<sub>⭐ 如果觉得有用，欢迎 Star！让更多人发现这个项目</sub>
</div>
