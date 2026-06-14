# Grok2API 自适应限流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让账号配额刷新与批量操作的并发按主机可用内存自适应收紧，修复导入大量账号触发整机 OOM 的 P0。

**Architecture:** 新增一个读 `/proc/meminfo` 的内存分层封顶函数 `effective_concurrency`；降低 `config.defaults.toml` 的并发默认值；把三处全量刷新扇出与资产/批量信号量、admin 批量并发统一过一遍该函数，并用 `run_batch` 已有的 `batch_size`+`pause_sec` 做波次停顿。

**Tech Stack:** Python 3.13、asyncio、unittest（dev 仅 ruff）、TOML 配置、uv。

**测试命令：**
- 单文件：`uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
- 全量：`uv run python -m unittest discover -s tests -v`

---

## 文件结构

- 新建 `app/platform/runtime/concurrency.py` —— `_mem_available_mb()` + `effective_concurrency()`
- 新建 `tests/test_concurrency.py` —— 上述函数与接线的单测
- 改 `config.defaults.toml` —— 降并发默认值 + 新增 `refresh_pause_sec`
- 改 `app/control/account/refresh.py` —— 三处全量扇出接入自适应 + 波次停顿
- 改 `app/dataplane/reverse/transport/assets.py` —— 两个全局信号量接入
- 改 `app/dataplane/reverse/transport/asset_upload.py` —— 上传信号量接入
- 改 `app/products/web/admin/batch.py` —— `_concurrency` 单一收口接入（tokens.py 复用同一函数）
- 改 `CLAUDE.md` —— 补一段简要事故记录
- 运维：服务器全抹重置 + 拉新镜像（手动 runbook，Task 6）

---

### Task 1: 内存分层封顶函数

**Files:**
- Create: `app/platform/runtime/concurrency.py`
- Test: `tests/test_concurrency.py`

- [ ] **Step 1: 写失败测试**

`tests/test_concurrency.py`：

```python
import unittest

from app.platform.runtime import concurrency


class EffectiveConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = concurrency._mem_available_mb

    def tearDown(self) -> None:
        concurrency._mem_available_mb = self._orig

    def _set_mem(self, mb):
        concurrency._mem_available_mb = lambda: mb

    def test_tiers(self):
        self._set_mem(320)
        self.assertEqual(concurrency.effective_concurrency(50), 2)
        self._set_mem(800)
        self.assertEqual(concurrency.effective_concurrency(50), 4)
        self._set_mem(1500)
        self.assertEqual(concurrency.effective_concurrency(50), 6)

    def test_high_mem_uses_configured(self):
        self._set_mem(4096)
        self.assertEqual(concurrency.effective_concurrency(8), 8)

    def test_cap_never_raises_configured(self):
        # 配置已经比分层上限低时，取较小值
        self._set_mem(1500)  # 上限 6
        self.assertEqual(concurrency.effective_concurrency(3), 3)

    def test_unreadable_trusts_config(self):
        concurrency._mem_available_mb = lambda: None
        self.assertEqual(concurrency.effective_concurrency(8), 8)

    def test_floor_one(self):
        self._set_mem(320)
        self.assertEqual(concurrency.effective_concurrency(0), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: FAIL（`ModuleNotFoundError: app.platform.runtime.concurrency`）

- [ ] **Step 3: 写最小实现**

`app/platform/runtime/concurrency.py`：

```python
"""按主机可用内存自适应收紧并发上限。

纯 Docker 容器（无 lxcfs）下 /proc/meminfo 反映的是宿主机内存，
正是发生全局 OOM 的那一层，因此这是正确的观测点。
"""


def _mem_available_mb() -> int | None:
    """读取 /proc/meminfo 的 MemAvailable（MiB）；读不到返回 None。"""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024  # kB -> MiB
    except OSError:
        return None
    return None


def effective_concurrency(configured: int) -> int:
    """把配置并发数按当前可用内存分层收紧；读不到内存则信任配置值。"""
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

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: PASS（5 个用例全过）

- [ ] **Step 5: 提交**

```bash
git add app/platform/runtime/concurrency.py tests/test_concurrency.py
git commit -m "feat: add memory-tiered effective_concurrency helper"
```

---

### Task 2: 降低并发默认值 + 新增波次停顿配置

**Files:**
- Modify: `config.defaults.toml`（`[account.refresh]`、`[batch]` 段）
- Test: `tests/test_concurrency.py`（追加一个加载默认配置的断言）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_concurrency.py` 顶部 import 后追加：

```python
import tomllib
from pathlib import Path


class DefaultsTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parent.parent
        with open(root / "config.defaults.toml", "rb") as f:
            self.cfg = tomllib.load(f)

    def test_refresh_defaults_lowered(self):
        self.assertLessEqual(self.cfg["account"]["refresh"]["usage_concurrency"], 8)
        self.assertIn("refresh_pause_sec", self.cfg["account"]["refresh"])

    def test_batch_defaults_lowered(self):
        b = self.cfg["batch"]
        for k in ("nsfw_concurrency", "refresh_concurrency",
                  "asset_list_concurrency", "asset_delete_concurrency"):
            self.assertLessEqual(b[k], 8, k)
        self.assertLessEqual(b["asset_upload_concurrency"], 4)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: FAIL（当前默认值为 50/10，断言不满足）

- [ ] **Step 3: 改默认值**

`config.defaults.toml` 中 `[account.refresh]` 段，把 `usage_concurrency = 50` 改为 `8`，并在该段追加一行：

```toml
usage_concurrency = 8
# 全量刷新每批之间的停顿秒数，让连接/缓冲释放（0 = 不停顿）
refresh_pause_sec = 0.5
```

`[batch]` 段改为：

```toml
[batch]
# 开启 NSFW 并发数（token 级，每个 token 需三步网络请求）
nsfw_concurrency         = 8
# 刷新 Usage 并发数（token 级）
refresh_concurrency      = 8
# 上传 Asset 并发数（全局，API 收到附件时触发，跨所有并发请求共享）
asset_upload_concurrency = 4
# 查询 Asset 并发数（全局，跨所有并发请求共享）
asset_list_concurrency   = 8
# 删除 Asset 并发数（全局，跨所有并发请求共享；也作为管理后台批量清理的 token 级默认值）
asset_delete_concurrency = 8
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add config.defaults.toml tests/test_concurrency.py
git commit -m "feat: lower default concurrency, add refresh_pause_sec"
```

---

### Task 3: refresh.py 三处全量扇出接入自适应 + 波次停顿

**Files:**
- Modify: `app/control/account/refresh.py`（import 段；`refresh_on_import` 167-172、`refresh_scheduled` 214-219、`refresh_tokens` 248-253）
- Test: `tests/test_concurrency.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_concurrency.py` 追加：

```python
import asyncio

from app.control.account import refresh as refresh_mod
from app.control.account.enums import AccountStatus
from app.control.account.models import AccountRecord


class _FakeRepo:
    def __init__(self, records):
        self._records = records

    async def get_accounts(self, tokens):
        return self._records


class RefreshWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_run_batch = refresh_mod.run_batch
        self._orig_eff = refresh_mod.effective_concurrency
        self.captured = {}

        async def _fake_run_batch(items, handler, **kwargs):
            self.captured.update(kwargs)
            return []

        refresh_mod.run_batch = _fake_run_batch
        refresh_mod.effective_concurrency = lambda c: 3

    def tearDown(self) -> None:
        refresh_mod.run_batch = self._orig_run_batch
        refresh_mod.effective_concurrency = self._orig_eff

    def test_refresh_on_import_passes_adaptive_kwargs(self):
        rec = AccountRecord(token="t-active", status=AccountStatus.ACTIVE)
        svc = refresh_mod.AccountRefreshService(_FakeRepo([rec]))
        asyncio.run(svc.refresh_on_import(["t-active"]))
        self.assertEqual(self.captured.get("concurrency"), 3)
        self.assertEqual(self.captured.get("batch_size"), 3)
        self.assertIsInstance(self.captured.get("pause_sec"), float)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: FAIL（当前 `run_batch` 调用未传 `batch_size`/`pause_sec`，`captured` 缺键；且 `effective_concurrency` 尚未在 refresh 模块导入 → AttributeError）

- [ ] **Step 3: 加 import**

`app/control/account/refresh.py` 在 `from app.platform.runtime.batch import run_batch` 之后加一行：

```python
from app.platform.runtime.batch import run_batch
from app.platform.runtime.concurrency import effective_concurrency
```

- [ ] **Step 4: 改 refresh_on_import（约 167-172 行）**

把：

```python
        concurrency = get_config("account.refresh.usage_concurrency", 50)
        results = await run_batch(
            active,
            lambda r: self._refresh_one(r, apply_fallback=True, bootstrap=True),
            concurrency=concurrency,
        )
```

改为：

```python
        conc = effective_concurrency(get_config("account.refresh.usage_concurrency", 8))
        pause = float(get_config("account.refresh.refresh_pause_sec", 0.5))
        results = await run_batch(
            active,
            lambda r: self._refresh_one(r, apply_fallback=True, bootstrap=True),
            concurrency=conc,
            batch_size=conc,
            pause_sec=pause,
        )
```

- [ ] **Step 5: 改 refresh_scheduled（约 214-219 行）**

把：

```python
        concurrency = get_config("account.refresh.usage_concurrency", 50)
        results = await run_batch(
            records,
            lambda r: self._refresh_one(r, apply_fallback=True),
            concurrency=concurrency,
        )
```

改为：

```python
        conc = effective_concurrency(get_config("account.refresh.usage_concurrency", 8))
        pause = float(get_config("account.refresh.refresh_pause_sec", 0.5))
        results = await run_batch(
            records,
            lambda r: self._refresh_one(r, apply_fallback=True),
            concurrency=conc,
            batch_size=conc,
            pause_sec=pause,
        )
```

- [ ] **Step 6: 改 refresh_tokens（约 248-253 行）**

把：

```python
        concurrency = get_config("account.refresh.usage_concurrency", 50)
        results = await run_batch(
            records,
            lambda r: self._refresh_one(r, bootstrap=True),
            concurrency=concurrency,
        )
```

改为：

```python
        conc = effective_concurrency(get_config("account.refresh.usage_concurrency", 8))
        pause = float(get_config("account.refresh.refresh_pause_sec", 0.5))
        results = await run_batch(
            records,
            lambda r: self._refresh_one(r, bootstrap=True),
            concurrency=conc,
            batch_size=conc,
            pause_sec=pause,
        )
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: PASS

- [ ] **Step 8: 跑全量回归**

Run: `uv run python -m unittest discover -s tests -v`
Expected: PASS（原有 `test_admin_batch_review_fixes`、`test_statsig_id` 不受影响）

- [ ] **Step 9: 提交**

```bash
git add app/control/account/refresh.py tests/test_concurrency.py
git commit -m "feat: adaptive concurrency + wave pauses in account refresh"
```

---

### Task 4: 资产信号量 + admin 批量并发接入

**Files:**
- Modify: `app/dataplane/reverse/transport/assets.py`（import + `_get_list_sem` 35-37、`_get_delete_sem` 42-44）
- Modify: `app/dataplane/reverse/transport/asset_upload.py`（import + `_get_upload_sem` 35-37）
- Modify: `app/products/web/admin/batch.py`（import + `_concurrency` 39-48）

- [ ] **Step 1: assets.py 接入**

加 import：

```python
from app.platform.config.snapshot import get_config
from app.platform.runtime.concurrency import effective_concurrency
```

`_get_list_sem` 内：

```python
        n = effective_concurrency(int(get_config("batch.asset_list_concurrency", 8)))
        _list_sem = asyncio.Semaphore(n)
```

`_get_delete_sem` 内：

```python
        n = effective_concurrency(int(get_config("batch.asset_delete_concurrency", 8)))
        _delete_sem = asyncio.Semaphore(n)
```

- [ ] **Step 2: asset_upload.py 接入**

加 import：

```python
from app.platform.config.snapshot import get_config
from app.platform.runtime.concurrency import effective_concurrency
```

`_get_upload_sem` 内：

```python
        n = effective_concurrency(int(get_config("batch.asset_upload_concurrency", 4)))
        _upload_sem = asyncio.Semaphore(n)
```

- [ ] **Step 3: batch.py 的 `_concurrency` 单一收口接入**

加 import（与现有 `from app.platform.config.snapshot import get_config` 同区）：

```python
from app.platform.runtime.concurrency import effective_concurrency
```

把 `_concurrency`（39-48 行）改为（默认 fallback 50→8，最终结果过一遍自适应）：

```python
def _concurrency(override: int | None, config_key: str, fallback: int = 8) -> int:
    """Resolve effective concurrency: query-param → config → fallback，再按内存自适应收紧。"""
    if override is not None:
        resolved = min(max(1, override), _MAX_BATCH_CONCURRENCY)
        return effective_concurrency(resolved)
    v = get_config(config_key, fallback)
    try:
        resolved = int(v)
    except (TypeError, ValueError):
        resolved = fallback
    resolved = min(max(1, resolved), _MAX_BATCH_CONCURRENCY)
    return effective_concurrency(resolved)
```

> 说明：`tokens.py:551` 从本模块 import `_concurrency`，因此该收口同时覆盖 tokens 批量 NSFW 路径，无需单独改 tokens.py。

- [ ] **Step 4: 写接线测试**

在 `tests/test_concurrency.py` 追加：

```python
from app.products.web.admin import batch as admin_batch


class AdminConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = admin_batch.effective_concurrency
        admin_batch.effective_concurrency = lambda c: min(c, 2)

    def tearDown(self) -> None:
        admin_batch.effective_concurrency = self._orig

    def test_concurrency_passes_through_adaptive(self):
        # override=10 → clamp 到 80 内 → 自适应封到 2
        self.assertEqual(admin_batch._concurrency(10, "batch.nsfw_concurrency"), 2)
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run python -m unittest discover -s tests -p "test_concurrency.py" -v`
Expected: PASS

- [ ] **Step 6: ruff 检查 + 全量回归**

Run: `uv run ruff check app/ tests/ && uv run python -m unittest discover -s tests -v`
Expected: ruff 无错误；测试全 PASS

- [ ] **Step 7: 提交**

```bash
git add app/dataplane/reverse/transport/assets.py app/dataplane/reverse/transport/asset_upload.py app/products/web/admin/batch.py tests/test_concurrency.py
git commit -m "feat: route asset/admin batch concurrency through effective_concurrency"
```

---

### Task 5: CLAUDE.md 事故记录

**Files:**
- Modify: `CLAUDE.md`（在「502 排查」段之后新增一节）

- [ ] **Step 1: 追加事故记录段**

在 `CLAUDE.md` 中新增：

```markdown
## 事故档案

### 2026-06-14 P0：导入 900+ 账号触发整机 OOM
- **现象**：导入 900+ 账号后整机内存抖动，443/sslh 上的 SSH 失联，人工重启恢复。
- **根因**：`refresh_on_import` 对全部账号以 50 路并发立即刷新配额，瞬时内存峰值
  突破 1.9 GiB 小机余量、灌满 swap → 内核全局 OOM 杀 `granian`。`mem_limit 1g`
  未生效（先爆主机全局内存，RSS 未触 cgroup 上限）。
- **放大器**：`restart: unless-stopped` 让 OOM 后自动重启再爆，形成自循环。
- **措施**：并发改为按 `/proc/meminfo` 内存分层自适应封顶（<512M→2 / <1G→4 / <2G→6），
  默认并发 50→8、asset_upload 10→4，全量刷新加波次停顿；账号分批导入。
- **教训**：小内存机重开前先 `docker stats` 压测；大批量导入分批观察。
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: record 2026-06-14 P0 OOM incident in CLAUDE.md"
```

---

### Task 6: 构建新镜像 + 服务器全抹重置（运维 runbook）

**Files:** 无代码改动；东京栈 `/opt/stack` 操作。前置：Task 1-5 已合到 `main` 并触发 CI。

- [ ] **Step 1: 合并并触发 CI**

```bash
git checkout main
git merge --no-ff fix/adaptive-concurrency
git push fork main
```

等待 fork CI（`Build Docker Image`）出新 `ghcr.io/ranshen1209/grok2api:latest`：

```bash
gh run list --repo Ranshen1209/grok2api --workflow=docker.yml --limit 1
```
Expected: 最近一条 `completed success`

- [ ] **Step 2: 备份后清空 data/（先备份，原则 2）**

```bash
ssh ssh-tokyo 'sudo tar -czf /opt/grok2api-data-pre-reset-$(date +%F-%H%M%S).tar.gz -C /opt/stack/grok2api data && rm -rf /opt/stack/grok2api/data/* /opt/stack/grok2api/data/.scheduler.lock && ls -la /opt/stack/grok2api/data/'
```
Expected: 归档生成；`data/` 清空

- [ ] **Step 3: 拉新镜像并重建容器**

```bash
ssh ssh-tokyo 'cd /opt/stack && docker compose pull grok2api && docker compose up -d grok2api'
```
> `docker compose up -d` 按 compose 重建，自动恢复 `restart: unless-stopped`（覆盖此前手动设的 `--restart=no`）。

- [ ] **Step 4: 验证健康 + 空池低占用**

```bash
ssh ssh-tokyo 'cd /opt/stack && sleep 20 && docker compose ps grok2api && docker stats --no-stream grok2api'
```
Expected: `Up (healthy)`；空池下 MEM 占用低（远低于 1g）

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://grok2api.sakrylle.com/health
```
Expected: `200`

- [ ] **Step 5: 分批导入验证（人工）**

先导入 100 号，观察：

```bash
ssh ssh-tokyo 'docker stats --no-stream grok2api; uptime'
```
Expected: load 平稳、MEM 不逼近上限后，再继续下一批。

---

## Self-Review

**Spec coverage：**
- §3.1 内存分层封顶 → Task 1 ✓
- §3.2 降默认值 + refresh_pause_sec → Task 2 ✓
- §3.3 波次停顿（refresh 三处）→ Task 3 ✓
- §3.4 资产/批量信号量 + admin 批量 → Task 4 ✓
- §6 上线 + 全抹重置 → Task 6 ✓；CLAUDE.md 事故补记（§6.4）→ Task 5 ✓
- §5 测试 → Task 1/2/3/4 的单测覆盖 effective_concurrency 分层、默认值、refresh 接线、admin 收口 ✓

**Placeholder 扫描：** 无 TBD/TODO；每个代码步骤均给出完整代码与期望输出。

**类型/命名一致性：** `effective_concurrency(configured:int)->int`、`_mem_available_mb()->int|None` 在各 Task 一致引用；`_concurrency` 签名与调用点（batch.py 270/307/329、tokens.py 573）保持兼容（仅改默认 fallback 与内部收口，签名不变）。

**已知边界：** 资产全局信号量惰性创建一次，自适应在创建时点取值（非持续重算）；可接受，后续如需热更新再迭代。
