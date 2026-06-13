# Grok Registrar — 批量注册机设计文档

**日期**: 2026-06-13
**状态**: 已批准
**项目路径**: `/Users/cervine/Documents/Program/Grok Register`

---

## 概述

Grok Registrar 是一个独立的 Web 服务，用于批量注册 **console.x.ai 免费账号**，自动获取 SSO Token，输出格式兼容 Grok2API 一键导入。服务于残障人士平等使用 AI 权益的场景。

### 核心依赖服务

| 服务 | 用途 | 凭证 |
|:--|:--|:--|
| moemail.app | 临时邮箱，接收验证邮件 | API Key: 已提供 |
| Capsolver | Turnstile 人机验证自动求解 | API Key: 用户提供 |
| Mihomo | 代理内核，提供多 IP 出口 | 用户上传 yaml 配置 |

---

## 技术架构

### 技术选型

| 层 | 选型 | 原因 |
|:--|:--|:--|
| Web 框架 | FastAPI + Granian | 与 Grok2API 一致，高性能 ASGI |
| 浏览器自动化 | Playwright (Chromium) | 最稳定的反检测生态 |
| 任务队列 | 自研 SQLite-backed JobQueue | 零外部依赖、持久化、断点续传 |
| 前端 | 纯静态 HTML/JS（内嵌 FastAPI） | 单服务部署，无额外构建 |
| ORM | SQLAlchemy + aiosqlite | 异步、轻量 |
| 日志 | loguru | 与 Grok2API 一致 |

### 架构分层

```
app/
├── platform/    基础设施（配置、日志、存储、错误）
├── control/     控制平面（任务调度器、代理选择器、导出格式化）
├── engine/      核心注册引擎（7 步流水线、浏览器池、Capsolver/email 客户端）
├── products/    对外 REST API
└── statics/     Web 管理面板前端
```

### 与 Grok2API 的关系

- **独立部署**，不耦合 Grok2API 代码
- 通过统一的 JSON 导出格式对接：`{"basic": [{"token": "sso_...", "tags": []}]}`
- 可部署在同一台机器，端口区分（如 Grok2API :8000，Registrar :8100）

---

## 注册流水线（7 阶段）

```
S1: 生成邮箱 → S2: 打开注册页 → S3: 过 Turnstile → S4: 提交邮箱
                                                          ↓
S7: 提取 SSO ← S6: 提交验证码 ← S5: 轮询邮件等验证码
```

### 阶段详情

| 阶段 | 操作 | 超时 | 失败处理 |
|:--|:--|:--|:--|
| **S1** | `POST /api/emails/generate`，随机前缀，expiryTime=0 | 10s | 重试 3 次指数退避 |
| **S2** | Playwright 启动 Chromium，绑定 Mihomo 代理，打开 `console.x.ai/signup` | 15s | 换代理重试 |
| **S3** | 检测 Turnstile → Capsolver createTask → 轮询 getTaskResult → 注入 token | 60s | 换策略重试 1 次 |
| **S4** | 填写邮箱 → 点击"发送验证码" | 10s | 重试 2 次 |
| **S5** | 每 5s 轮询 `GET /api/emails/{emailId}`，等待 Grok 验证邮件 | 120s | 重发验证码 2 次 |
| **S6** | 解析邮件 HTML 提取 6 位验证码 → 填入 → 提交 | 10s | 重新轮询 |
| **S7** | 等待跳转 → 读取 `sso` cookie → 清洗 token → 持久化 | 15s | 重新获取 cookie |

### 浏览器实例池

- 最大并发数 N（可配置，默认 10，最大 80）
- 每个 Chromium 实例通过 `--proxy-server` 绑定唯一 Mihomo 代理节点
- 空闲 30s 自动回收，队列积压 ≥3 时预热启动新实例
- 同一代理 IP 同一时间只允许 1 个注册任务（防止 rate-limit）

---

## 容错与代理管理

### 代理选择

- 加权轮询，`fail_count` 越高权重越低
- 连续失败 5 次 → 熔断 30 分钟
- IP 去重：同一代理不并发注册
- 启动前 TCP 连通性预检

### 注册失败处理

```
单次失败 → stage 重试计数 < 3 且可重试 → 同一 stage 换代理重试
         → 代理节点失败 → node.fail_count++ → 选新节点 → 从失败 stage 继续
         → 总重试 > 3 或不可重试 → 标记 registration.failed → task.failed++
```

### 断点续传

- 每条 `registration` 记录有 `stage` 字段
- 暂停/重启后从当前 `stage` 恢复，不重复消耗已完成的步骤
- 邮箱地址保留在 `email_id` 字段，不重复创建

### Capsolver 集成

```
createTask(sitekey, pageUrl, proxyInfo) 
  → 轮询 getTaskResult(taskId)，每 2s，超时 60s
  → 成功 → 注入 token 提交表单
  → 失败 → 换策略重试 1 次 → 仍失败 → 标记 failed
```

---

## 数据模型

### proxy_configs

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| id | TEXT PK | UUID |
| name | TEXT | 配置名称 |
| config_yaml | TEXT | Mihomo 原始 yaml |
| proxy_count | INTEGER | 解析出的节点数 |
| enabled | BOOLEAN | 启用状态 |
| created_at | INTEGER | 创建时间(ms) |
| updated_at | INTEGER | 更新时间(ms) |

### proxy_nodes

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| id | TEXT PK | UUID |
| config_id | TEXT FK | 所属配置 |
| name | TEXT | 节点名 |
| type | TEXT | socks5 / http |
| host | TEXT | 地址 |
| port | INTEGER | 端口 |
| status | TEXT | unknown / active / failed / banned |
| fail_count | INTEGER | 累计失败次数 |
| last_used_at | INTEGER | 最后使用时间(ms) |

### tasks

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| id | TEXT PK | UUID |
| name | TEXT | 任务名称 |
| status | TEXT | pending / running / paused / completed / failed |
| total | INTEGER | 目标总数 |
| completed | INTEGER | 成功数 |
| failed | INTEGER | 失败数 |
| concurrency | INTEGER | 并行数（默认 10，最大 80） |
| proxy_config_id | TEXT FK | 代理配置 |
| created_at | INTEGER | 创建时间(ms) |
| updated_at | INTEGER | 更新时间(ms) |

### registrations

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| id | TEXT PK | UUID |
| task_id | TEXT FK | 所属任务 |
| stage | TEXT | 当前阶段 s1..s7 |
| status | TEXT | pending / running / success / failed |
| email_addr | TEXT | moemail 邮箱地址 |
| email_id | TEXT | moemail 邮箱 UUID |
| sso_token | TEXT | 提取的 SSO Token |
| error_msg | TEXT | 失败原因 |
| attempts | INTEGER | 当前 stage 重试次数 |
| proxy_node_id | TEXT | 使用的代理节点 |
| started_at | INTEGER | 开始时间(ms) |
| finished_at | INTEGER | 完成时间(ms) |

---

## REST API

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| `POST` | `/api/v1/tasks` | 创建注册任务 |
| `GET` | `/api/v1/tasks` | 任务列表（分页） |
| `GET` | `/api/v1/tasks/{id}` | 任务详情 + 进度 |
| `POST` | `/api/v1/tasks/{id}/pause` | 暂停任务 |
| `POST` | `/api/v1/tasks/{id}/resume` | 恢复任务 |
| `DELETE` | `/api/v1/tasks/{id}` | 删除任务及关联记录 |
| `GET` | `/api/v1/accounts` | 已注册账号分页列表 |
| `GET` | `/api/v1/accounts/export` | 导出 Grok2API JSON 格式 |
| `POST` | `/api/v1/proxy/configs` | 上传 Mihomo 配置 |
| `GET` | `/api/v1/proxy/configs` | 代理配置列表 |
| `GET` | `/api/v1/proxy/nodes` | 代理节点状态 |
| `GET` | `/api/v1/system/status` | 系统状态（Capsolver 余额、运行中任务数等） |

### Grok2API 导出格式

```json
{
  "basic": [
    {"token": "sso_abc123def456...", "tags": []},
    {"token": "sso_ghi789jkl012...", "tags": []}
  ]
}
```

直接兼容 Grok2API Admin → 账号管理 → 批量导入。

---

## Web 管理面板

### 页面结构

1. **仪表盘** — 总注册数、成功/失败/进行中统计卡片
2. **任务管理** — 新建任务（目标数、并发数、代理配置选择）、启动/暂停/删除操作、实时进度条
3. **账号库** — 筛选（按任务、状态）、搜索、分页列表、一键导出 Grok2API 格式
4. **代理管理** — 上传 Mihomo yaml、查看解析节点、节点状态（active/failed/banned）
5. **设置** — Capsolver API Key、moemail API Key/Domain、默认并发数等全局配置

### 前端技术

- 纯 HTML/CSS/JS，无框架
- 从 FastAPI `/static` 挂载提供
- 通过 fetch API 调用同源 `/api/v1/*` 端点
- 任务进度 3s 自动轮询刷新

---

## 部署

### 环境要求

- Python 3.13+
- Playwright Chromium 浏览器（首次运行 `playwright install chromium`）
- Mihomo 代理内核（用户自行部署，提供配置文件即可）
- Capsolver 账户余额

### Docker 部署（推荐）

```bash
cd "/Users/cervine/Documents/Program/Grok Register"
docker compose up -d
```

### 本地开发

```bash
uv sync
uv run granian --interface asgi --host 0.0.0.0 --port 8100 --workers 1 app.main:app
```

### 环境变量

| 变量 | 说明 | 默认值 |
|:--|:--|:--|
| `CAPSOLVER_API_KEY` | Capsolver API Key | (必填) |
| `MOEMAIL_API_KEY` | moemail API Key | (必填) |
| `MOEMAIL_BASE_URL` | moemail API 地址 | `https://moemail.sakrylle.com` |
| `MOEMAIL_DOMAIN` | 邮箱域名 | `moemail.app` |
| `REGISTRAR_PORT` | 监听端口 | `8100` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `DATA_DIR` | 数据目录 | `./data` |

---

## 实施范围

### 包含

- 完整的 Web 管理面板 + REST API
- 7 步注册流水线引擎
- Playwright 浏览器池管理
- Capsolver + moemail 集成
- Mihomo yaml 解析与代理绑定
- SQLite 持久化任务队列
- 断点续传与失败重试
- Grok2API 格式导出
- Docker 部署配置

### 不包含

- console.x.ai 注册页面变更的自动适配（需后续维护）
- 付费账号（SuperGrok）注册
- 多语言 i18n
- 用户权限/登录系统
