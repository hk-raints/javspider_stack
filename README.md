# 🎬 JavSpider Stack v2.1

<div align="center">

**本地优先的 JavBus 数据管家 — 封面永不失效、磁力永不断链**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://sqlalchemy.org)
[![Alembic](https://img.shields.io/badge/Alembic-1.13+-orange.svg)](https://alembic.sqlalchemy.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

> **English summary:** JavBus metadata manager with local-first design. Features **Asynchronous Architecture** (FastAPI + SQLAlchemy Async), **Alembic Migrations**, **Docker Support**, **Pydantic Settings**, and **API Key Security**. High-performance crawler with WebSocket real-time progress.

---

> ⚠️ **免责声明 / Disclaimer**
>
> 本项目仅供技术学习与个人研究使用。使用前请确认遵守所在地区的相关法律法规，并尊重目标网站的服务条款。
> 本工具不存储、不传播任何受版权保护的媒体内容，数据库仅在本地使用，不得用于商业用途。
>
> *This project is for educational and personal research purposes only.*

---

## ✨ 核心亮点 (v2.1 升级)

- ⚡ **全异步架构**: 核心逻辑全面迁移至 `async/await`，基于 `FastAPI` + `SQLAlchemy Async` + `aiosqlite`，性能大幅提升。
- 📦 **Docker 一键部署**: 支持 Docker 与 Docker Compose，环境配置零负担。
- 🛡️ **安全增强**: 引入可选的 `API Key` 鉴权，保护您的私有数据接口。
- 🔧 **数据库迁移**: 集成 `Alembic` 管理数据库 Schema，版本升级更安全。
- 🌐 **环境隔离**: 使用 `Pydantic Settings` 与 `.env` 管理配置，支持开发/生产环境一键切换。
- 📡 **实时看板**: WebSocket 驱动的任务调度系统，实时掌握爬取动态。

---

## 🚀 快速开始

### 方法 A：使用 Docker (推荐)
1. 复制 `.env.example` 为 `.env` 并按需配置：
   ```bash
   cp .env.example .env
   ```
2. 启动服务：
   ```bash
   docker-compose up -d
   ```
访问：**http://localhost:8088**

### 方法 B：本地启动
1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```
2. **初始化/升级数据库**:
   ```bash
   alembic upgrade head
   ```
3. **启动**:
   ```bash
   python start.py
   ```

---

## 🏗️ 现代化项目结构

```
javspider_stack/
├── app/                        # 核心应用逻辑 (New v2.1)
│   ├── api/                    # 异步 REST API 路由
│   ├── core/                   # 核心组件 (Async HttpClient, Security)
│   ├── db/                     # 数据库层 (Async Session, Alembic Config)
│   ├── schemas/                # Pydantic 数据验证模型
│   ├── services/               # 异步业务逻辑 (Crawler, Task Queue)
│   └── main.py                 # 异步应用入口
├── alembic/                    # 数据库迁移脚本
├── config.py                   # 基于 Pydantic Settings 的配置管理
├── Dockerfile                  # 容器镜像构建
└── docker-compose.yml          # 多容器编排
```

---

## ⚙️ 配置说明 (.env)

编辑 `.env` 文件调整运行参数：

| 配置项 | 说明 |
|--------|------|
| `API_KEY` | 访问 API 所需的密钥（留空则不启用鉴权） |
| `DB_URL` | 数据库连接字符串（默认 aiosqlite） |
| `HTTP_PROXY` | 爬虫使用的代理地址 |
| `SERVER_PORT` | Web 服务端口（默认 8088） |

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！
- 🔧 **代码贡献**：Fork → 新建分支 → 提交 PR
- ⭐ 如果觉得有用，欢迎 **Star**！让更多人发现这个项目。

---

## 📄 License

[MIT](LICENSE) © Raints
