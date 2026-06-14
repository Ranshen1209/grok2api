# Grok2API 自适应限流设计（事故修复）

- 日期：2026-06-14
- 状态：待评审
- 关联事故：2026-06-14 P0 —— 导入 900+ 账号触发整机 OOM

## 1. 背景

2026-06-14 在东京 API 栈（1.9 GiB 内存 / 2 vCPU）部署 grok2api 后，一次性导入 900+ 账号，
触发整机全局 OOM（`constraint=CONSTRAINT_NONE ... global_oom`，内核杀掉 `granian`），
2 核被内存抖动拖入 iowait，连带 443/sslh 上的 SSH 一并失联，最终人工重启服务器恢复。

根因：`app/control/account/refresh.py::refresh_on_import()` 在导入后立即对全部账号做配额刷新，
经 `run_batch(active, _refresh_one, concurrency=usage_concurrency)` 以 **50 路并发**扇出，
每个任务持有 curl_cffi 会话与响应缓冲；900 账号 × 50 并发的瞬时内存峰值突破主机仅剩的
约 850 MiB 余量，灌满 1.4 GiB swap 后抖动 → OOM。

`mem_limit 1g` 未生效：被杀时 granian RSS 仅 ~430 MiB（未触 cgroup 上限），先爆的是**主机全局内存**。
同样的全量扇出还存在于 `refresh_scheduled()`（周期刷新）与 `refresh_tokens()`（手动刷新）。

## 2. 目标与非目标

### 目标
1. 让并发刷新对**主机可用内存自适应**：小机自动收紧，大机维持原速。
2. 降低 `config.defaults.toml` 的并发默认值，避免开箱即危险。
3. 全量刷新分批 + 波间停顿，让连接/缓冲在波次之间释放。
4. 服务器端 grok2api 全抹重建：清空 `data/`，用新镜像起空池。

### 非目标
- 不改账号选号/调度算法，不动刷新周期语义（basic/super/heavy interval）。
- 不引入新的第三方依赖（如 psutil）。
- 不做精确的逐任务内存计量（脆弱且收益低）。

## 3. 设计

三层叠加：**降默认值** +**内存分层上限** +**波次停顿**。

### 3.1 内存分层上限（核心，新增模块）

新增 `app/platform/runtime/concurrency.py`：

```python
"""按主机可用内存自适应收紧并发上限。"""

def _mem_available_mb() -> int | None:
    """读取 /proc/meminfo 的 MemAvailable（MiB）。

    纯 Docker 容器（无 lxcfs）下 /proc/meminfo 反映的是**主机**内存，
    正是发生 OOM 的那一层，因此这是正确的观测点。读不到时返回 None。
    """
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024  # kB -> MiB
    except OSError:
        return None
    return None


def effective_concurrency(configured: int) -> int:
    """把配置的并发数按当前可用内存分层收紧。读不到内存则信任配置值。"""
    configured = max(1, int(configured))
    avail = _mem_available_mb()
    if avail is None:
        return configured
    if avail < 512:
        cap = 2
    elif avail < 1024:
        cap = 4
    elif avail < 2048:
        cap = 6
    else:
        return configured
    return min(configured, cap)
```

分层表：

| MemAvailable | 并发上限 |
|---|---|
| < 512 MiB | 2 |
| < 1 GiB | 4 |
| < 2 GiB | 6 |
| ≥ 2 GiB | 用配置值 |

设计权衡：分层（而非 `available/est_task_mb`）避免脆弱的逐任务内存估算，便于推理与回归。
每次调用实时读取 `/proc/meminfo`，因此随主机负载动态变化。

### 3.2 降默认值（`config.defaults.toml`）

| 配置项 | 原值 | 新值 |
|---|---|---|
| `[account.refresh] usage_concurrency` | 50 | 8 |
| `[batch] nsfw_concurrency` | 50 | 8 |
| `[batch] refresh_concurrency` | 50 | 8 |
| `[batch] asset_list_concurrency` | 50 | 8 |
| `[batch] asset_delete_concurrency` | 50 | 8 |
| `[batch] asset_upload_concurrency` | 10 | 4 |

新增（用于全量刷新的波次停顿）：

```toml
[account.refresh]
# 全量刷新每批之间的停顿秒数，让连接/缓冲释放（0 = 不停顿）
refresh_pause_sec = 0.5
```

`max_inflight`（单号并发上限，默认 8）不变。

### 3.3 波次停顿（复用 run_batch 现有能力）

`run_batch` 已支持 `batch_size` 与 `pause_sec`，当前调用方未使用。改造三处全量扇出，使其
按 `effective_concurrency` 作为每波大小、`refresh_pause_sec` 作为波间停顿处理：

`app/control/account/refresh.py`，`refresh_on_import` / `refresh_scheduled` / `refresh_tokens`
统一改为：

```python
from app.platform.runtime.concurrency import effective_concurrency

conc = effective_concurrency(get_config("account.refresh.usage_concurrency", 8))
pause = float(get_config("account.refresh.refresh_pause_sec", 0.5))
results = await run_batch(
    records,
    lambda r: self._refresh_one(...),
    concurrency=conc,
    batch_size=conc,      # 每波 conc 个，跑满即停顿
    pause_sec=pause,
)
```

效果：任意时刻在途任务 ≤ `conc`，每波结束 sleep `pause`，连接池与响应缓冲在波间释放。
900 账号在 1.9 GiB 机上 → `conc=6`，约 150 波 × 0.5s，后台刷新耗时增加可接受。

### 3.4 资产/批量全局信号量

`app/dataplane/reverse/transport/assets.py`、`asset_upload.py` 的全局 `Semaphore(n)` 在
惰性创建时把 `n` 经 `effective_concurrency` 收紧；`app/products/web/admin/batch.py` 与
`tokens.py` 的批量管理操作同样在取并发数后过一遍 `effective_concurrency`。

## 4. 影响面与边界

- 仅收紧并发与增加波间停顿，不改变刷新结果正确性，仅延长后台刷新墙钟时间。
- 大主机（MemAvailable ≥ 2 GiB）行为不变（直接用配置值），无性能回退。
- `/proc/meminfo` 读不到时回退到配置值（保守地信任运维配置）。
- 周期刷新与导入刷新共用同一收紧逻辑，覆盖所有全量扇出路径。

## 5. 测试

- 单元测试 `effective_concurrency`：构造 `_mem_available_mb` 返回 320/800/1500/4096/None，
  断言上限为 2/4/6/configured/configured。
- 单元测试 `run_batch` 的 `batch_size`+`pause_sec` 分波与顺序（已有结构，补断言）。
- 冒烟：本地以小账号集触发 `refresh_on_import`，确认按波执行、无异常。

## 6. 上线与服务器重置（全抹）

1. 代码改动 + 单测通过 → commit → push 到 `Ranshen1209/grok2api` 的 main → CI 出新 `latest`。
2. 服务器（grok2api 当前已 `exited restart=no`）：
   - 先备份再删（CLAUDE.md 原则 2）：`tar -czf` 归档 `data/` 后清空 `/opt/stack/grok2api/data/*`。
   - `docker compose pull grok2api`（拉新镜像）。
   - `docker compose up -d grok2api`（按 compose 重建，恢复 `restart: unless-stopped`）。
   - 验证 `healthy`、空池下 `docker stats` 内存占用低。
3. 账号后续**分批**导入（每批观察 `docker stats`），不再一次性 900。
4. 在 `CLAUDE.md` 增补一段简要事故记录（根因 + 教训 + 自适应限流措施）。

## 7. 回滚

- 镜像：compose `image:` 指回上一个 `latest` 摘要即可。
- 配置：默认值改动随镜像回滚；运行期可在 WebUI 临时调并发。
