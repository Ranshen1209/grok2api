# CLAUDE.md — Grok2API 运维

Grok2API：grok.com / console.x.ai 能力的 OpenAI / Anthropic 兼容网关（FastAPI，多账号池）。
容器 `grok2api`，镜像 `ghcr.io/jiujiu532/grok2api:latest`，容器内 HTTP 跑 `8000`。
有状态：`./data/accounts.db`（SQLite 账号池）、`./logs`。流式 SSE 服务。

部署归口 **Sakrylle 东京 API 栈**（`ssh ssh-tokyo`，`/opt/stack`），完整手册见 vault 的
`serverops` skill 与 `20 Work/ServerOps/**`。本文件只放本服务的运维速查。

## 第一原则

1. **先读后写**：改配置前先 `docker compose config` / `cat` 看真实状态，别凭记忆。
2. **改前先备份**：动 `data/accounts.db` / `.env` / `docker compose pull` 前先归档。
3. **破坏性操作先确认**：`down -v`、删卷、`prune -a`、force-recreate、改证书/DNS/防火墙——先说影响再动手。
4. **机密不外泄**：`.env`（含 SSO token / API key）`chmod 600`，按 key 名引用，绝不回显、不进 git。
5. **改完必验证**：健康检查 + 公网入口都过；`docker exec nginx nginx -t` 必过才 reload。
6. **失败两次停下诊断根因**，别在同一错误上反复打补丁。

## 架构不变量（接入东京栈时）

- 公网只开 `80`/`443`，`sslh` 在 443 分流，TLS 由 nginx 终止；容器内只跑 HTTP。
- 并入单一 `/opt/stack/docker-compose.yml`，nginx 配置在 `/opt/stack/nginx/conf.d/`。
- 复用 `*.sakrylle.com` 通配证书（`/opt/stack/certs/`）。
- 子域名 Cloudflare **DNS only**（不开橙云），避免打断流式。
- nginx `depends_on` 必须加 `grok2api`，否则首次 reload 可能 502。
- 流式反代必须 `proxy_buffering off` + `proxy_cache off`，超时拉到 300–600s。

## 常用运维

```bash
# 状态
ssh ssh-tokyo 'cd /opt/stack && docker compose ps grok2api'
ssh ssh-tokyo 'cd /opt/stack && docker compose logs --tail=50 grok2api'

# 升级（latest tag，先记版本作回滚锚点）
ssh ssh-tokyo 'docker inspect grok2api --format="{{.Config.Image}}"'
ssh ssh-tokyo 'sudo tar -czf /opt/grok2api-data-$(date +%F).tar.gz /opt/stack/grok2api/data'   # 备份账号池
ssh ssh-tokyo 'cd /opt/stack && docker compose pull grok2api && docker compose up -d grok2api'
ssh ssh-tokyo 'cd /opt/stack && docker compose ps grok2api && docker compose logs --tail=50 grok2api'

# 改 nginx conf.d 后
ssh ssh-tokyo 'docker exec nginx nginx -t && docker exec nginx nginx -s reload'
```

## 502 排查

```bash
ssh ssh-tokyo 'cd /opt/stack && docker compose logs --tail=50 grok2api'   # 容器是否 Up/healthy
ssh ssh-tokyo 'docker exec nginx curl -sI http://grok2api:8000/'          # 容器内可达性
```

顺序：① `grok2api` 容器是否 Up（不是就看自身日志，多半凭证/配置/账号池权限）→
② nginx `depends_on` 漏没漏 `grok2api` → ③ 容器名/端口与 `proxy_pass` 是否一致 →
④ DNS 是否解析到东京高防 IP `154.36.159.42`。

## 事故档案

### 2026-06-14 P0：导入 900+ 账号触发整机 OOM
- **现象**：导入 900+ 账号后整机内存抖动，443/sslh 上的 SSH 失联，人工重启恢复。
- **根因**：`refresh_on_import` 对全部账号以 50 路并发立即刷新配额，瞬时内存峰值突破
  1.9 GiB 小机余量、灌满 swap → 内核全局 OOM 杀 `granian`。`mem_limit 1g` 未生效
  （先爆主机全局内存，被杀时 RSS 仅 ~430 MiB，未触 cgroup 上限）。
- **放大器**：`restart: unless-stopped` 让 OOM 后自动重启再爆，形成自循环。
- **措施**：并发改为按 `/proc/meminfo` 内存分层自适应封顶（<512M→2 / <1G→4 / <2G→6，
  ≥2G 用配置值），默认并发 50→8、asset_upload 10→4，全量刷新加波次停顿；账号分批导入。
- **教训**：小内存机重开前先 `docker stats` 压测；大批量账号分批导入并观察 load/MEM。

## 新增接线（首次部署，标准 6 步）

1. `mkdir -p /opt/stack/grok2api/{data,logs}`，`.env` `chmod 600`
2. compose 追加 `grok2api` 服务块（加 `mem_limit` / healthcheck / logging json-file 10m×3）
3. `nginx/conf.d/grok2api.conf`：80 跳 443 + `8443 ssl` 反代到 `grok2api:8000`，复用通配证书，
   流式三件套（buffering off / cache off / 超时 300–600s）
4. nginx `depends_on` 加 `grok2api`
5. Cloudflare 加 A 记录指向 `154.36.159.42`，**DNS only**
6. `docker compose up -d grok2api` → `nginx -t && nginx -s reload` → 验证健康 + 公网入口

## 本地开发

```bash
uv sync                                    # 装依赖（Python 3.13+）
cp .env.example .env                       # 配置，chmod 600
docker compose up -d                       # 本地起服务（默认 8000）
docker compose logs -f grok2api
```
