# Grok Registrar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone web service for batch-registering console.x.ai free accounts with automated Turnstile solving, email verification, and Mihomo proxy rotation, outputting SSO tokens in Grok2API-compatible format.

**Architecture:** FastAPI + Granian HTTP server with SQLite-backed job queue, Playwright browser pool for web automation, Capsolver for Turnstile solving, and moemail.app for temporary email. Pure HTML/JS admin panel served from `/static`.

**Tech Stack:** Python 3.13+, FastAPI, Granian, SQLAlchemy+aiosqlite, Playwright, loguru, orjson

**Target path:** `/Users/cervine/Documents/Program/Grok Registar`

---

## File Structure Map

```
Grok Registar/
├── pyproject.toml
├── .env.example
├── config.defaults.toml
├── docker-compose.yml
├── Dockerfile
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app factory + lifespan
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── config.py                 # TOML config loader
│   │   ├── logging.py                # loguru setup
│   │   ├── storage.py                # SQLite async engine + session
│   │   └── errors.py                 # AppError exception hierarchy
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py                   # declarative base + async session factory
│   │   ├── task.py                   # Task ORM
│   │   ├── registration.py           # Registration ORM
│   │   └── proxy.py                  # ProxyConfig + ProxyNode ORM
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── moemail.py                # moemail.app HTTP client
│   │   ├── capsolver.py              # Capsolver API client
│   │   ├── mihomo_parser.py          # Mihomo YAML → proxy_nodes
│   │   ├── browser_pool.py           # Playwright instance pool
│   │   ├── pipeline.py               # 7-stage orchestrator
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── base.py               # BaseStage abstract class
│   │       ├── s1_generate_email.py
│   │       ├── s2_open_signup.py
│   │       ├── s3_solve_turnstile.py
│   │       ├── s4_submit_email.py
│   │       ├── s5_poll_inbox.py
│   │       ├── s6_verify_code.py
│   │       └── s7_extract_sso.py
│   ├── control/
│   │   ├── __init__.py
│   │   ├── scheduler.py              # Task dispatch + concurrency control
│   │   ├── proxy_selector.py         # Weighted round-robin node selector
│   │   └── exporter.py               # Grok2API JSON export
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                 # APIRouter aggregation
│   │   ├── tasks.py                  # /api/v1/tasks/*
│   │   ├── accounts.py               # /api/v1/accounts/*
│   │   ├── proxy.py                  # /api/v1/proxy/*
│   │   └── system.py                 # /api/v1/system/*
│   └── statics/
│       ├── index.html                # Admin SPA shell
│       ├── css/
│       │   └── app.css
│       └── js/
│           └── app.js                # Vanilla JS SPA
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_moemail.py
│   ├── test_mihomo_parser.py
│   ├── test_capsolver.py
│   ├── test_pipeline.py
│   └── test_api.py
└── scripts/
    └── entrypoint.sh
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `config.defaults.toml`
- Create: `app/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "grok-registrar"
version = "0.1.0"
description = "Batch console.x.ai account registrar with Grok2API-compatible export"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "aiohttp>=3.14.0",
    "fastapi>=0.119.0",
    "granian>=2.7.4",
    "loguru>=0.7.3",
    "orjson>=3.11.4",
    "playwright>=1.55.0",
    "pydantic>=2.12.3",
    "python-dotenv>=1.1.1",
    "sqlalchemy[asyncio]>=2.0.46",
    "aiosqlite>=0.21.0",
    "pyyaml>=6.0",
    "tomli-w>=1.2.0",
]

[dependency-groups]
dev = [
    "httpx>=0.28",
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "ruff>=0.15.0",
]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write .env.example**

```bash
# Capsolver
CAPSOLVER_API_KEY=

# moemail
MOEMAIL_API_KEY=
MOEMAIL_BASE_URL=https://moemail.sakrylle.com
MOEMAIL_DOMAIN=moemail.app

# Server
REGISTRAR_PORT=8100
LOG_LEVEL=INFO
DATA_DIR=./data
```

- [ ] **Step 3: Write config.defaults.toml**

```toml
[server]
host = "0.0.0.0"
port = 8100

[task]
default_concurrency = 10
max_concurrency = 80
max_retries = 3

[proxy]
# Mihomo config is uploaded via UI; these are runtime defaults
node_ban_threshold = 5
node_ban_duration_minutes = 30

[capsolver]
api_key = ""
poll_interval_seconds = 2
task_timeout_seconds = 60

[moemail]
api_key = ""
base_url = "https://moemail.sakrylle.com"
domain = "moemail.app"

[logging]
level = "INFO"
```

- [ ] **Step 4: Write app/__init__.py**

```python
"""Grok Registrar — batch console.x.ai account registration service."""
```

- [ ] **Step 5: Install dependencies and verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv sync
```
Expected: All packages install without error.

- [ ] **Step 6: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git init && git add -A && git commit -m "feat: project scaffold"
```

---

### Task 2: Platform Layer — Config, Logging, Errors, Storage

**Files:**
- Create: `app/platform/__init__.py`
- Create: `app/platform/config.py`
- Create: `app/platform/logging.py`
- Create: `app/platform/errors.py`
- Create: `app/platform/storage.py`

- [ ] **Step 1: Write app/platform/__init__.py**

```python
"""Platform utilities — config, logging, storage, error types."""
```

- [ ] **Step 2: Write app/platform/config.py**

```python
"""TOML-based configuration loader with env-var override support.

Reads config.defaults.toml, merges with data/config.toml (runtime overrides),
and applies env var overrides (GROKREG_ prefix).
"""

import os
from pathlib import Path
from typing import Any

import tomllib
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "config.defaults.toml"


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._loaded = False

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def load(self) -> None:
        with open(_DEFAULT_PATH, "rb") as f:
            self._data = tomllib.load(f)

        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        runtime_path = data_dir / "config.toml"
        if runtime_path.exists():
            with open(runtime_path, "rb") as f:
                runtime = tomllib.load(f)
                self._data = _deep_merge(self._data, runtime)

        self._apply_env_overrides()
        self._loaded = True

    def _apply_env_overrides(self) -> None:
        for key, val in os.environ.items():
            if not key.startswith("GROKREG_"):
                continue
            parts = key[8:].lower().split("__")
            if len(parts) < 2:
                continue
            section = self._data
            for part in parts[:-1]:
                if part not in section:
                    section[part] = {}
                section = section[part]
            section[parts[-1]] = self._coerce(val)

    @staticmethod
    def _coerce(val: str) -> Any:
        low = val.lower()
        if low in ("true", "false"):
            return low == "true"
        try:
            return int(val)
        except ValueError:
            pass
        try:
            return float(val)
        except ValueError:
            pass
        return val

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def get_str(self, key: str, default: str = "") -> str:
        val = self._data
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part, default)
            else:
                return default
        return str(val) if val is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get_str(key, str(default))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._data
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part, default)
            else:
                return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")


config = Config()
```

- [ ] **Step 3: Write app/platform/logging.py**

```python
"""Loguru-based logging setup."""

import sys

from loguru import logger


def setup_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )


__all__ = ["logger", "setup_logging"]
```

- [ ] **Step 4: Write app/platform/errors.py**

```python
"""Application error hierarchy."""

from enum import Enum


class ErrorKind(str, Enum):
    VALIDATION = "validation_error"
    NOT_FOUND = "not_found"
    UPSTREAM = "upstream_error"
    INTERNAL = "internal_error"
    CONFLICT = "conflict"


class AppError(Exception):
    def __init__(self, message: str, kind: ErrorKind = ErrorKind.INTERNAL, status: int = 500):
        self.message = message
        self.kind = kind
        self.status = status
        super().__init__(message)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, ErrorKind.VALIDATION, 400)


class NotFoundError(AppError):
    def __init__(self, message: str):
        super().__init__(message, ErrorKind.NOT_FOUND, 404)


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, ErrorKind.CONFLICT, 409)


class UpstreamError(AppError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message, ErrorKind.UPSTREAM, status)
```

- [ ] **Step 5: Write app/platform/storage.py**

```python
"""SQLite async engine and session factory."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _db_path() -> str:
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "registrar.db")


_engine = create_async_engine(
    f"sqlite+aiosqlite:///{_db_path()}",
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def create_tables() -> None:
    from app.models.base import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await _engine.dispose()
```

- [ ] **Step 6: Install and verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv sync && uv run python -c "from app.platform.config import config; config.load(); print('config ok')"
```
Expected: `config ok`

- [ ] **Step 7: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: platform layer — config, logging, errors, storage"
```

---

### Task 3: SQLAlchemy Data Models

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/base.py`
- Create: `app/models/task.py`
- Create: `app/models/registration.py`
- Create: `app/models/proxy.py`

- [ ] **Step 1: Write app/models/__init__.py**

```python
"""SQLAlchemy ORM models."""
from app.models.base import Base, get_session
from app.models.task import Task
from app.models.registration import Registration
from app.models.proxy import ProxyConfig, ProxyNode

__all__ = ["Base", "get_session", "Task", "Registration", "ProxyConfig", "ProxyNode"]
```

- [ ] **Step 2: Write app/models/base.py**

```python
"""Declarative base and session utilities."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.platform.storage import async_session_factory, get_session  # noqa: E402

__all__ = ["Base", "get_session"]
```

- [ ] **Step 3: Write app/models/task.py**

```python
"""Task model — a batch registration job."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | paused | completed | failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    concurrency: Mapped[int] = mapped_column(Integer, default=10)
    proxy_config_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "concurrency": self.concurrency,
            "proxy_config_id": self.proxy_config_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
```

- [ ] **Step 4: Write app/models/registration.py**

```python
"""Registration model — one account registration attempt."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(30), default="pending")  # pending | s1 | s2 | ... | s7
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | success | failed
    email_addr: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    email_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    sso_token: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    proxy_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "stage": self.stage,
            "status": self.status,
            "email_addr": self.email_addr,
            "email_id": self.email_id,
            "sso_token": self.sso_token,
            "error_msg": self.error_msg,
            "attempts": self.attempts,
            "proxy_node_id": self.proxy_node_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
```

- [ ] **Step 5: Write app/models/proxy.py**

```python
"""Proxy configuration and node models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProxyConfig(Base):
    __tablename__ = "proxy_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), default="")
    config_yaml: Mapped[str] = mapped_column(Text, default="")
    proxy_count: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "proxy_count": self.proxy_count,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProxyNode(Base):
    __tablename__ = "proxy_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id: Mapped[str] = mapped_column(String(36), ForeignKey("proxy_configs.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[str] = mapped_column(String(10), default="http")  # http | socks5
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="unknown")  # unknown | active | failed | banned
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "config_id": self.config_id,
            "name": self.name,
            "type": self.type,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "fail_count": self.fail_count,
            "last_used_at": self.last_used_at,
        }
```

- [ ] **Step 6: Verify models import**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.models import Task, Registration, ProxyConfig, ProxyNode; print('models ok')"
```
Expected: `models ok`

- [ ] **Step 7: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: SQLAlchemy data models — Task, Registration, ProxyConfig, ProxyNode"
```

---

### Task 4: moemail API Client

**Files:**
- Create: `tests/__init__.py` (empty file)
- Create: `tests/conftest.py`
- Create: `tests/test_moemail.py`
- Create: `app/engine/__init__.py`
- Create: `app/engine/moemail.py`

- [ ] **Step 1: Write tests/conftest.py**

```python
"""Shared test fixtures."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

- [ ] **Step 2: Write tests/test_moemail.py — failing test**

```python
"""Tests for moemail API client."""

import pytest
from app.engine.moemail import MoeMailClient


def test_client_requires_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        MoeMailClient(api_key="", base_url="https://example.com")


def test_client_stores_config():
    client = MoeMailClient(api_key="test-key", base_url="https://example.com", domain="test.app")
    assert client.api_key == "test-key"
    assert client.base_url == "https://example.com"
    assert client.domain == "test.app"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_moemail.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine.moemail'`

- [ ] **Step 4: Write app/engine/__init__.py**

```python
"""Registration engine — external API clients, browser pool, pipeline stages."""
```

- [ ] **Step 5: Write app/engine/moemail.py**

```python
"""MoeMail.app API client for temporary email management.

API docs: https://docs.moemail.app/
"""

from dataclasses import dataclass

import aiohttp


@dataclass
class InboxMessage:
    id: str
    from_address: str
    subject: str
    content: str
    html: str
    received_at: int


class MoeMailClient:
    def __init__(self, *, api_key: str, base_url: str, domain: str = "moemail.app"):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.domain = domain

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def generate_email(self, name: str = "", expiry_time: int = 0) -> dict:
        """Create a temporary email address.

        Returns: {"id": "uuid", "email": "user@domain"}
        expiry_time: 0 = permanent, 3600000 = 1h, 86400000 = 1d, 604800000 = 7d
        """
        payload = {"expiryTime": expiry_time, "domain": self.domain}
        if name:
            payload["name"] = name
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/emails/generate",
                headers=self._headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"MoeMail generate_email failed: status={resp.status} body={data}")
                return data

    async def get_messages(self, email_id: str, cursor: str = "") -> dict:
        """List messages for an inbox.

        Returns: {"messages": [...], "nextCursor": "...", "total": N}
        """
        url = f"{self.base_url}/api/emails/{email_id}"
        if cursor:
            url += f"?cursor={cursor}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"MoeMail get_messages failed: status={resp.status}")
                return data

    async def get_message(self, email_id: str, message_id: str) -> InboxMessage:
        """Get the full content of a single message."""
        url = f"{self.base_url}/api/emails/{email_id}/{message_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"MoeMail get_message failed: status={resp.status}")
                msg = data["message"]
                return InboxMessage(
                    id=msg["id"],
                    from_address=msg["from_address"],
                    subject=msg["subject"],
                    content=msg["content"],
                    html=msg.get("html", ""),
                    received_at=msg["received_at"],
                )

    async def delete_email(self, email_id: str) -> bool:
        """Delete an inbox."""
        url = f"{self.base_url}/api/emails/{email_id}"
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                return data.get("success", False)

    async def poll_for_message(
        self,
        email_id: str,
        *,
        timeout_seconds: int = 120,
        poll_interval: int = 5,
        subject_contains: str = "",
    ) -> InboxMessage | None:
        """Poll inbox until a matching message arrives or timeout.

        Returns the first message whose subject contains ``subject_contains``, or None on timeout.
        """
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            data = await self.get_messages(email_id)
            messages = data.get("messages", [])
            for m in messages:
                subject = m.get("subject", "")
                if not subject_contains or subject_contains.lower() in subject.lower():
                    return await self.get_message(email_id, m["id"])
            await asyncio.sleep(poll_interval)
        return None
```

- [ ] **Step 6: Run tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_moemail.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: moemail API client"
```

---

### Task 5: Capsolver API Client

**Files:**
- Create: `tests/test_capsolver.py`
- Create: `app/engine/capsolver.py`

- [ ] **Step 1: Write tests/test_capsolver.py — failing test**

```python
"""Tests for Capsolver API client."""

import pytest
from app.engine.capsolver import CapsolverClient, CapsolverError


def test_client_requires_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        CapsolverClient(api_key="")


def test_client_stores_config():
    client = CapsolverClient(api_key="CAP-12345")
    assert client.api_key == "CAP-12345"


def test_create_task_payload_structure():
    client = CapsolverClient(api_key="CAP-12345")
    payload = client._build_turnstile_payload(
        sitekey="0x4AAAA",
        page_url="https://console.x.ai/signup",
        proxy="http://user:pass@1.2.3.4:8080",
    )
    assert payload["task"]["type"] == "AntiTurnstileTaskProxyLess"
    assert payload["task"]["websiteKey"] == "0x4AAAA"
    assert payload["task"]["websiteURL"] == "https://console.x.ai/signup"
    assert payload["task"]["proxy"] == "http://user:pass@1.2.3.4:8080"


def test_create_task_payload_no_proxy():
    client = CapsolverClient(api_key="CAP-12345")
    payload = client._build_turnstile_payload(
        sitekey="0x4AAAA",
        page_url="https://console.x.ai/signup",
    )
    assert "proxy" not in payload["task"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_capsolver.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine.capsolver'`

- [ ] **Step 3: Write app/engine/capsolver.py**

```python
"""Capsolver API client for Turnstile solving.

Capsolver API: https://docs.capsolver.com/
"""

import asyncio
from dataclasses import dataclass, field

import aiohttp


class CapsolverError(Exception):
    pass


@dataclass
class CapsolverClient:
    api_key: str
    base_url: str = "https://api.capsolver.com"
    poll_interval: float = 2.0
    task_timeout: float = 60.0

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key is required")

    def _build_turnstile_payload(
        self,
        sitekey: str,
        page_url: str,
        proxy: str | None = None,
    ) -> dict:
        task: dict = {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteKey": sitekey,
            "websiteURL": page_url,
        }
        if proxy:
            task["type"] = "AntiTurnstileTask"
            task["proxy"] = proxy
        return {
            "clientKey": self.api_key,
            "task": task,
        }

    async def create_task(
        self,
        sitekey: str,
        page_url: str,
        proxy: str | None = None,
    ) -> str:
        """Create a Turnstile solving task. Returns taskId."""
        payload = self._build_turnstile_payload(sitekey, page_url, proxy)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/createTask",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if data.get("errorId") != 0:
                    raise CapsolverError(
                        f"createTask failed: {data.get('errorCode')} - {data.get('errorDescription')}"
                    )
                return data["taskId"]

    async def get_task_result(self, task_id: str) -> dict:
        """Get the result of a solving task."""
        payload = {"clientKey": self.api_key, "taskId": task_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/getTaskResult",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if data.get("errorId") != 0:
                    raise CapsolverError(
                        f"getTaskResult failed: {data.get('errorCode')} - {data.get('errorDescription')}"
                    )
                return data

    async def solve_turnstile(
        self,
        sitekey: str,
        page_url: str,
        proxy: str | None = None,
    ) -> str:
        """Solve a Turnstile challenge end-to-end. Returns the token string.

        Raises CapsolverError on timeout or failure.
        """
        task_id = await self.create_task(sitekey, page_url, proxy)
        deadline = asyncio.get_event_loop().time() + self.task_timeout
        while asyncio.get_event_loop().time() < deadline:
            result = await self.get_task_result(task_id)
            status = result.get("status", "")
            if status == "ready":
                solution = result.get("solution", {})
                token = solution.get("token") or solution.get("gRecaptchaResponse")
                if not token:
                    raise CapsolverError(f"No token in solution: {result}")
                return token
            if status == "failed":
                raise CapsolverError(f"Task {task_id} failed: {result}")
            await asyncio.sleep(self.poll_interval)
        raise CapsolverError(f"Turnstile solving timed out after {self.task_timeout}s")
```

- [ ] **Step 4: Run tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_capsolver.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Capsolver API client"
```

---

### Task 6: Mihomo YAML Parser

**Files:**
- Create: `tests/test_mihomo_parser.py`
- Create: `app/engine/mihomo_parser.py`

- [ ] **Step 1: Write tests/test_mihomo_parser.py**

```python
"""Tests for Mihomo YAML config parser."""

from app.engine.mihomo_parser import parse_mihomo_config

SAMPLE_YAML = """
proxies:
  - name: "jp-node-1"
    type: socks5
    server: 1.2.3.4
    port: 1080
  - name: "us-node-http"
    type: http
    server: 5.6.7.8
    port: 8080
    username: user1
    password: pass1
  - name: "hk-node"
    type: ss
    server: 10.0.0.1
    port: 8388
  - name: "sg-socks5"
    type: socks5
    server: 192.168.1.1
    port: 9999
"""


def test_parse_extracts_http_socks5():
    nodes = parse_mihomo_config(SAMPLE_YAML)
    assert len(nodes) == 3  # ss type excluded, http+socks5 only

    jp = nodes[0]
    assert jp["name"] == "jp-node-1"
    assert jp["type"] == "socks5"
    assert jp["host"] == "1.2.3.4"
    assert jp["port"] == 1080

    us = nodes[1]
    assert us["name"] == "us-node-http"
    assert us["type"] == "http"
    assert us["host"] == "5.6.7.8"
    assert us["port"] == 8080
    assert "username" in us.get("extra", {})
    assert us["extra"]["username"] == "user1"


def test_parse_empty_yaml():
    nodes = parse_mihomo_config("proxies: []")
    assert nodes == []


def test_parse_no_proxies_key():
    nodes = parse_mihomo_config("other: value")
    assert nodes == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_mihomo_parser.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine.mihomo_parser'`

- [ ] **Step 3: Write app/engine/mihomo_parser.py**

```python
"""Mihomo (Clash Meta) YAML config parser.

Extracts HTTP and SOCKS5 proxy nodes from a Mihomo config file.
"""

import yaml


def parse_mihomo_config(yaml_content: str) -> list[dict]:
    """Parse a Mihomo YAML config and return HTTP/SOCKS5 proxy nodes.

    Each node dict: {"name": str, "type": "http"|"socks5", "host": str, "port": int, "extra": dict}
    Shadowsocks, VMess, Trojan, and other types are skipped (not usable by Playwright).
    """
    try:
        config = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        return []

    proxies = config.get("proxies", [])
    if not isinstance(proxies, list):
        return []

    nodes = []
    for p in proxies:
        if not isinstance(p, dict):
            continue
        ptype = str(p.get("type", "")).lower()
        if ptype not in ("http", "socks5"):
            continue

        server = p.get("server", "")
        port = p.get("port", 0)
        if not server or not port:
            continue

        extra = {}
        for k in ("username", "password", "tls", "skip-cert-verify", "sni"):
            if k in p:
                extra[k] = p[k]

        nodes.append({
            "name": str(p.get("name", f"{server}:{port}")),
            "type": ptype,
            "host": str(server),
            "port": int(port),
            "extra": extra,
        })

    return nodes
```

- [ ] **Step 4: Run tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_mihomo_parser.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Mihomo YAML config parser"
```

---

### Task 7: Proxy Selector (Weighted Round-Robin)

**Files:**
- Create: `app/control/__init__.py`
- Create: `app/control/proxy_selector.py`

- [ ] **Step 1: Write app/control/__init__.py**

```python
"""Control plane — task scheduling, proxy selection, export formatting."""
```

- [ ] **Step 2: Write tests/test_mihomo_parser.py — add selector tests**

Add to existing file:

```python
from unittest.mock import MagicMock


def test_proxy_selector_returns_nodes():
    from app.control.proxy_selector import ProxySelector
    nodes = [
        {"id": "n1", "type": "http", "host": "1.1.1.1", "port": 8080, "fail_count": 0},
        {"id": "n2", "type": "socks5", "host": "2.2.2.2", "port": 1080, "fail_count": 0},
    ]
    selector = ProxySelector(nodes)
    result = selector.select()
    assert result is not None


def test_proxy_selector_prefers_low_fail_count():
    from app.control.proxy_selector import ProxySelector
    nodes = [
        {"id": "good", "type": "http", "host": "1.1.1.1", "port": 8080, "fail_count": 0},
        {"id": "bad", "type": "socks5", "host": "2.2.2.2", "port": 1080, "fail_count": 100},
    ]
    selector = ProxySelector(nodes)
    results = [selector.select()["id"] for _ in range(20)]
    assert results.count("good") > results.count("bad")


def test_proxy_selector_returns_none_when_empty():
    from app.control.proxy_selector import ProxySelector
    selector = ProxySelector([])
    assert selector.select() is None
```

- [ ] **Step 3: Write app/control/proxy_selector.py**

```python
"""Weighted round-robin proxy node selector.

Nodes with higher fail_count get exponentially lower weight.
Banned nodes (fail_count >= threshold) are excluded.
"""

import random
from typing import Any


class ProxySelector:
    def __init__(self, nodes: list[dict[str, Any]], ban_threshold: int = 5):
        self._nodes = nodes
        self._ban_threshold = ban_threshold
        self._index = 0

    @property
    def active_nodes(self) -> list[dict[str, Any]]:
        return [
            n for n in self._nodes
            if int(n.get("fail_count", 0)) < self._ban_threshold
        ]

    def select(self) -> dict[str, Any] | None:
        active = self.active_nodes
        if not active:
            return None

        weights = []
        for n in active:
            fc = int(n.get("fail_count", 0))
            w = 1.0 / (2 ** fc)
            weights.append(w)

        total = sum(weights)
        r = random.random() * total
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return active[i]

        return active[-1]

    def get_playwright_proxy_string(self, node: dict[str, Any]) -> str:
        """Build Playwright --proxy-server string from a node dict."""
        ptype = node["type"]
        host = node["host"]
        port = node["port"]
        extra = node.get("extra", {})
        user = extra.get("username", "")
        pwd = extra.get("password", "")

        if user and pwd:
            return f"{ptype}://{user}:{pwd}@{host}:{port}"
        return f"{ptype}://{host}:{port}"
```

- [ ] **Step 4: Run tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_mihomo_parser.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: weighted round-robin proxy selector"
```

---

### Task 8: Playwright Browser Pool

**Files:**
- Create: `app/engine/browser_pool.py`

- [ ] **Step 1: Write app/engine/browser_pool.py**

```python
"""Playwright browser instance pool with proxy binding.

Manages a pool of Chromium instances, each bound to a unique proxy node.
Supports idle timeout, pre-warming, and concurrent instance limit.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@dataclass
class BrowserPoolConfig:
    max_instances: int = 10
    idle_timeout_seconds: float = 30.0
    prewarm_threshold: int = 3


class BrowserPool:
    def __init__(self, config: BrowserPoolConfig | None = None):
        self._cfg = config or BrowserPoolConfig()
        self._instances: dict[str, Browser] = {}
        self._in_use: set[str] = set()
        self._last_used: dict[str, float] = {}
        self._playwright = None
        self._lock = asyncio.Lock()

    async def _get_playwright(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def _launch_browser(self, proxy_string: str) -> Browser:
        pw = await self._get_playwright()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                f"--proxy-server={proxy_string}",
            ],
        )
        logger.debug("browser launched: proxy={}", proxy_string)
        return browser

    async def acquire(self, proxy_string: str, node_id: str) -> tuple[BrowserContext, Page]:
        async with self._lock:
            if node_id in self._in_use:
                raise RuntimeError(f"Proxy node {node_id} already in use")

            browser = self._instances.get(node_id)
            if browser is None or not browser.is_connected():
                if len(self._instances) >= self._cfg.max_instances:
                    await self._reap_idle()
                    if len(self._instances) >= self._cfg.max_instances:
                        raise RuntimeError("Browser pool exhausted")

                browser = await self._launch_browser(proxy_string)
                self._instances[node_id] = browser

            self._in_use.add(node_id)
            self._last_used[node_id] = asyncio.get_event_loop().time()

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await context.new_page()
        return context, page

    async def release(self, node_id: str) -> None:
        async with self._lock:
            self._in_use.discard(node_id)
            self._last_used[node_id] = asyncio.get_event_loop().time()

    async def invalidate(self, node_id: str) -> None:
        """Close and remove a browser instance (called on proxy failure)."""
        async with self._lock:
            self._in_use.discard(node_id)
            browser = self._instances.pop(node_id, None)
            self._last_used.pop(node_id, None)
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _reap_idle(self) -> None:
        now = asyncio.get_event_loop().time()
        idle_ids = [
            nid for nid in self._instances
            if nid not in self._in_use
            and now - self._last_used.get(nid, 0) >= self._cfg.idle_timeout_seconds
        ]
        for nid in idle_ids:
            browser = self._instances.pop(nid, None)
            self._last_used.pop(nid, None)
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            logger.debug("browser reaped: node_id={}", nid)

    async def close_all(self) -> None:
        for nid, browser in list(self._instances.items()):
            try:
                await browser.close()
            except Exception:
                pass
        self._instances.clear()
        self._in_use.clear()
        self._last_used.clear()
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @property
    def active_count(self) -> int:
        return len(self._instances)

    @property
    def in_use_count(self) -> int:
        return len(self._in_use)
```

- [ ] **Step 2: Verify import**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.browser_pool import BrowserPool, BrowserPoolConfig; print('pool ok')"
```
Expected: `pool ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Playwright browser pool with proxy binding"
```

---

### Task 9: Pipeline Base Stage + S1 (Generate Email)

**Files:**
- Create: `app/engine/stages/__init__.py`
- Create: `app/engine/stages/base.py`
- Create: `app/engine/stages/s1_generate_email.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write tests/test_pipeline.py**

```python
"""Tests for registration pipeline and stages."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.stages.s1_generate_email import S1GenerateEmail


@pytest.mark.asyncio
async def test_s1_generates_email():
    mock_moemail = AsyncMock()
    mock_moemail.generate_email.return_value = {"id": "email-uuid", "email": "test@moemail.app"}

    stage = S1GenerateEmail(moemail_client=mock_moemail)
    ctx = {}  # fresh context
    result = await stage.run(ctx)

    assert result["email_id"] == "email-uuid"
    assert result["email_addr"] == "test@moemail.app"
    mock_moemail.generate_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_s1_uses_random_prefix():
    mock_moemail = AsyncMock()
    mock_moemail.generate_email.return_value = {"id": "uuid", "email": "x@moemail.app"}

    stage = S1GenerateEmail(moemail_client=mock_moemail)
    await stage.run({})

    call_args = mock_moemail.generate_email.call_args
    assert "name" in call_args.kwargs
    assert len(call_args.kwargs["name"]) == 8  # random 8-char prefix
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_pipeline.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write app/engine/stages/__init__.py**

```python
"""Registration pipeline stages — one class per stage."""
from app.engine.stages.s1_generate_email import S1GenerateEmail
from app.engine.stages.s2_open_signup import S2OpenSignup
from app.engine.stages.s3_solve_turnstile import S3SolveTurnstile
from app.engine.stages.s4_submit_email import S4SubmitEmail
from app.engine.stages.s5_poll_inbox import S5PollInbox
from app.engine.stages.s6_verify_code import S6VerifyCode
from app.engine.stages.s7_extract_sso import S7ExtractSSO

__all__ = [
    "S1GenerateEmail", "S2OpenSignup", "S3SolveTurnstile",
    "S4SubmitEmail", "S5PollInbox", "S6VerifyCode", "S7ExtractSSO",
]
```

- [ ] **Step 4: Write app/engine/stages/base.py**

```python
"""Base class for pipeline stages."""

from abc import ABC, abstractmethod
from typing import Any


class StageError(Exception):
    def __init__(self, stage: str, message: str, retryable: bool = True):
        self.stage = stage
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{stage}] {message}")


class BaseStage(ABC):
    name: str = "base"

    @abstractmethod
    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Execute this stage. Mutates and returns ctx with new keys."""
        ...
```

- [ ] **Step 5: Write app/engine/stages/s1_generate_email.py**

```python
"""S1: Generate a temporary email address via moemail."""

import random
import string
from typing import Any

from app.engine.stages.base import BaseStage, StageError


class S1GenerateEmail(BaseStage):
    name = "s1_generate_email"

    def __init__(self, moemail_client):
        self._moemail = moemail_client

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        try:
            result = await self._moemail.generate_email(name=prefix, expiry_time=0)
        except Exception as e:
            raise StageError(self.name, f"Failed to generate email: {e}", retryable=True) from e

        ctx["email_id"] = result["id"]
        ctx["email_addr"] = result["email"]
        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 6: Run tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/test_pipeline.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: pipeline base stage + S1 (generate email)"
```

---

### Task 10: S2 — Open Signup Page

**Files:**
- Create: `app/engine/stages/s2_open_signup.py`

- [ ] **Step 1: Write app/engine/stages/s2_open_signup.py**

```python
"""S2: Open console.x.ai signup page with Playwright."""

from typing import Any

from app.engine.stages.base import BaseStage, StageError

SIGNUP_URL = "https://console.x.ai/signup"


class S2OpenSignup(BaseStage):
    name = "s2_open_signup"

    def __init__(self, browser_pool):
        self._pool = browser_pool

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        proxy_string = ctx.get("proxy_string", "")
        node_id = ctx.get("proxy_node_id", "")

        try:
            context, page = await self._pool.acquire(proxy_string, node_id)
        except Exception as e:
            raise StageError(self.name, f"Browser acquire failed: {e}", retryable=True) from e

        ctx["_browser_context"] = context
        ctx["_page"] = page

        try:
            await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)  # Let JS initialize
        except Exception as e:
            await self._pool.invalidate(node_id)
            ctx.pop("_browser_context", None)
            ctx.pop("_page", None)
            raise StageError(self.name, f"Page load failed: {e}", retryable=True) from e

        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s2_open_signup import S2OpenSignup; print('s2 ok')"
```
Expected: `s2 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S2 — open console.x.ai signup page"
```

---

### Task 11: S3 — Solve Turnstile via Capsolver

**Files:**
- Create: `app/engine/stages/s3_solve_turnstile.py`

- [ ] **Step 1: Write app/engine/stages/s3_solve_turnstile.py**

```python
"""S3: Detect and solve Cloudflare Turnstile on the signup page."""

from typing import Any

from app.engine.stages.base import BaseStage, StageError


class S3SolveTurnstile(BaseStage):
    name = "s3_solve_turnstile"

    TURNSTILE_SELECTOR = "iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com']"
    TURNSTILE_SITEKEY_PATTERN = 'sitekey='

    def __init__(self, capsolver_client):
        self._capsolver = capsolver_client

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        page = ctx.get("_page")
        if page is None:
            raise StageError(self.name, "No page context available", retryable=False)

        proxy_string = ctx.get("proxy_string")

        try:
            # Wait for Turnstile iframe to appear
            await page.wait_for_selector(self.TURNSTILE_SELECTOR, timeout=10000)
        except Exception:
            # Turnstile might not be present (already solved or different flow)
            ctx["turnstile_token"] = ""
            ctx["stage"] = self.name
            return ctx

        # Extract sitekey from page source
        page_url = page.url
        content = await page.content()
        sitekey = ""
        if self.TURNSTILE_SITEKEY_PATTERN in content:
            idx = content.index(self.TURNSTILE_SITEKEY_PATTERN) + len(self.TURNSTILE_SITEKEY_PATTERN)
            sitekey = content[idx:idx+64].split('&')[0].split('"')[0].split("'")[0]

        if not sitekey:
            # Try to get from iframe src
            try:
                iframe = await page.query_selector(self.TURNSTILE_SELECTOR)
                if iframe:
                    src = await iframe.get_attribute("src") or ""
                    if self.TURNSTILE_SITEKEY_PATTERN in src:
                        idx = src.index(self.TURNSTILE_SITEKEY_PATTERN) + len(self.TURNSTILE_SITEKEY_PATTERN)
                        sitekey = src[idx:].split("&")[0]
            except Exception:
                pass

        if not sitekey:
            ctx["turnstile_token"] = ""
            ctx["stage"] = self.name
            return ctx

        try:
            token = await self._capsolver.solve_turnstile(
                sitekey=sitekey,
                page_url=page_url,
                proxy=proxy_string if proxy_string else None,
            )
        except Exception as e:
            raise StageError(self.name, f"Capsolver failed: {e}", retryable=True) from e

        # Inject token into Turnstile and trigger callback
        await page.evaluate(
            """(token) => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                if (input) input.value = token;
                if (window.turnstile) {
                    window.turnstile.render = function() {};
                }
            }""",
            token,
        )

        ctx["turnstile_token"] = token
        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s3_solve_turnstile import S3SolveTurnstile; print('s3 ok')"
```
Expected: `s3 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S3 — solve Turnstile via Capsolver"
```

---

### Task 12: S4 — Submit Email on Signup Form

**Files:**
- Create: `app/engine/stages/s4_submit_email.py`

- [ ] **Step 1: Write app/engine/stages/s4_submit_email.py**

```python
"""S4: Fill in the email address and click send verification code."""

from typing import Any

from app.engine.stages.base import BaseStage, StageError


class S4SubmitEmail(BaseStage):
    name = "s4_submit_email"

    # Common selectors for console.x.ai signup (may need updates if x.ai changes UI)
    EMAIL_INPUT_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='email' i]",
        "input[placeholder*='Email']",
    ]
    SUBMIT_BUTTON_SELECTORS = [
        "button[type='submit']",
        "button:has-text('Continue')",
        "button:has-text('Sign up')",
        "button:has-text('Next')",
        "button:has-text('Send code')",
        "button:has-text('Send')",
    ]

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        page = ctx.get("_page")
        if page is None:
            raise StageError(self.name, "No page context", retryable=False)

        email_addr = ctx.get("email_addr", "")
        if not email_addr:
            raise StageError(self.name, "No email address in context", retryable=False)

        try:
            # Find and fill email input
            email_input = None
            for sel in self.EMAIL_INPUT_SELECTORS:
                email_input = await page.query_selector(sel)
                if email_input:
                    break
            if not email_input:
                raise StageError(self.name, "Email input not found on page", retryable=True)

            await email_input.click()
            await email_input.fill(email_addr)
            await page.wait_for_timeout(500)

            # Find and click submit button
            button = None
            for sel in self.SUBMIT_BUTTON_SELECTORS:
                button = await page.query_selector(sel)
                if button:
                    break
            if not button:
                raise StageError(self.name, "Submit button not found", retryable=True)

            await button.click()
            await page.wait_for_timeout(3000)  # Wait for "check your email" message

        except StageError:
            raise
        except Exception as e:
            raise StageError(self.name, f"Form interaction failed: {e}", retryable=True) from e

        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s4_submit_email import S4SubmitEmail; print('s4 ok')"
```
Expected: `s4 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S4 — submit email on signup form"
```

---

### Task 13: S5 — Poll Inbox for Verification Email

**Files:**
- Create: `app/engine/stages/s5_poll_inbox.py`

- [ ] **Step 1: Write app/engine/stages/s5_poll_inbox.py**

```python
"""S5: Poll the moemail inbox waiting for the Grok verification code email."""

import re
from typing import Any

from app.engine.stages.base import BaseStage, StageError


class S5PollInbox(BaseStage):
    name = "s5_poll_inbox"

    def __init__(self, moemail_client):
        self._moemail = moemail_client

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        email_id = ctx.get("email_id", "")
        if not email_id:
            raise StageError(self.name, "No email_id in context", retryable=False)

        msg = await self._moemail.poll_for_message(
            email_id,
            timeout_seconds=120,
            poll_interval=5,
            subject_contains="",  # Match any email (Grok verification emails have various subjects)
        )

        if msg is None:
            raise StageError(self.name, "Timed out waiting for verification email", retryable=True)

        # Try to extract 6-digit code from HTML or text
        code = self._extract_code(msg.html or msg.content or "")
        if not code:
            raise StageError(self.name, "Could not extract verification code from email", retryable=True)

        ctx["verification_code"] = code
        ctx["verification_email_id"] = msg.id
        ctx["stage"] = self.name
        return ctx

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract a 6-digit verification code from email content."""
        # Look for 6 consecutive digits (common pattern)
        match = re.search(r'\b(\d{6})\b', text)
        if match:
            return match.group(1)
        # Look for 4-8 digit code patterns
        match = re.search(r'\b(\d{4,8})\b', text)
        if match:
            return match.group(1)
        return ""
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s5_poll_inbox import S5PollInbox; print('s5 ok')"
```
Expected: `s5 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S5 — poll inbox for verification email"
```

---

### Task 14: S6 — Submit Verification Code

**Files:**
- Create: `app/engine/stages/s6_verify_code.py`

- [ ] **Step 1: Write app/engine/stages/s6_verify_code.py**

```python
"""S6: Enter the verification code and complete email verification."""

from typing import Any

from app.engine.stages.base import BaseStage, StageError


class S6VerifyCode(BaseStage):
    name = "s6_verify_code"

    CODE_INPUT_SELECTORS = [
        "input[type='text'][maxlength='6']",
        "input[data-input='code']",
        "input[placeholder*='code' i]",
        "input[placeholder*='Code']",
        "input[name='code']",
        "input[aria-label*='code' i]",
    ]

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        page = ctx.get("_page")
        if page is None:
            raise StageError(self.name, "No page context", retryable=False)

        code = ctx.get("verification_code", "")
        if not code:
            raise StageError(self.name, "No verification code in context", retryable=False)

        try:
            # Find the code input
            code_input = None
            for sel in self.CODE_INPUT_SELECTORS:
                code_input = await page.query_selector(sel)
                if code_input:
                    break

            if not code_input:
                # Try generic text input approach
                all_inputs = await page.query_selector_all("input")
                for inp in all_inputs:
                    input_type = await inp.get_attribute("type") or ""
                    if input_type != "password":
                        code_input = inp
                        break

            if not code_input:
                raise StageError(self.name, "Code input not found", retryable=True)

            await code_input.click()
            await code_input.fill(code)
            await page.wait_for_timeout(500)

            # Try to auto-submit — some forms submit on 6 digits, others need button click
            await page.wait_for_timeout(2000)

            # Check if we need to click a continue/verify button
            submit_button = (
                await page.query_selector("button[type='submit']")
                or await page.query_selector("button:has-text('Continue')")
                or await page.query_selector("button:has-text('Verify')")
            )
            if submit_button:
                await submit_button.click()

            await page.wait_for_timeout(3000)

        except StageError:
            raise
        except Exception as e:
            raise StageError(self.name, f"Code submission failed: {e}", retryable=True) from e

        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s6_verify_code import S6VerifyCode; print('s6 ok')"
```
Expected: `s6 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S6 — submit verification code"
```

---

### Task 15: S7 — Extract SSO Token

**Files:**
- Create: `app/engine/stages/s7_extract_sso.py`

- [ ] **Step 1: Write app/engine/stages/s7_extract_sso.py**

```python
"""S7: Extract the SSO token from cookies after successful login."""

from typing import Any

from app.engine.stages.base import BaseStage, StageError


def clean_sso_token(raw: str) -> str:
    """Normalize SSO token — strip whitespace, unicode, 'sso=' prefix, non-ASCII."""
    trans_table = str.maketrans({
        "‐": "-", "‑": "-", "‒": "-",
        "–": "-", "—": "-", "−": "-",
        " ": " ", " ": " ", " ": " ",
        "​": "", "‌": "", "‍": "", "﻿": "",
    })
    token = str(raw or "").translate(trans_table)
    token = "".join(token.split())
    if token.startswith("sso="):
        token = token[4:]
    return token.encode("ascii", errors="ignore").decode("ascii")


class S7ExtractSSO(BaseStage):
    name = "s7_extract_sso"

    async def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        page = ctx.get("_page")
        if page is None:
            raise StageError(self.name, "No page context", retryable=False)

        try:
            # Wait for redirect after successful login (dashboard or home)
            await page.wait_for_url("**/console.x.ai/**", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass  # Might already be on the right page

        # Extract SSO cookie
        cookies = await page.context.cookies()
        sso_token = ""
        for cookie in cookies:
            if cookie.get("name") == "sso":
                sso_token = cookie.get("value", "")
                break

        if not sso_token:
            # Try localStorage fallback
            try:
                sso_token = await page.evaluate(
                    "() => localStorage.getItem('sso') || localStorage.getItem('ssoToken') || ''"
                )
            except Exception:
                pass

        sso_token = clean_sso_token(sso_token)

        # Reject tokens that are too short to be real
        if len(sso_token) < 20:
            raise StageError(self.name, f"SSO token too short ({len(sso_token)} chars), likely invalid", retryable=True)

        ctx["sso_token"] = sso_token
        ctx["stage"] = self.name
        return ctx
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.stages.s7_extract_sso import S7ExtractSSO, clean_sso_token; assert clean_sso_token(' sso=abc123 ') == 'abc123'; print('s7 ok')"
```
Expected: `s7 ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: S7 — extract SSO token from cookies"
```

---

### Task 16: Pipeline Orchestrator

**Files:**
- Create: `app/engine/pipeline.py`

- [ ] **Step 1: Write app/engine/pipeline.py**

```python
"""7-stage registration pipeline orchestrator.

Runs a single registration through all stages, handling retries,
proxy node feedback, and context persistence.
"""

from typing import Any

from loguru import logger

from app.engine.stages.base import StageError
from app.engine.stages.s1_generate_email import S1GenerateEmail
from app.engine.stages.s2_open_signup import S2OpenSignup
from app.engine.stages.s3_solve_turnstile import S3SolveTurnstile
from app.engine.stages.s4_submit_email import S4SubmitEmail
from app.engine.stages.s5_poll_inbox import S5PollInbox
from app.engine.stages.s6_verify_code import S6VerifyCode
from app.engine.stages.s7_extract_sso import S7ExtractSSO

STAGE_CLASSES = [
    S1GenerateEmail,
    S2OpenSignup,
    S3SolveTurnstile,
    S4SubmitEmail,
    S5PollInbox,
    S6VerifyCode,
    S7ExtractSSO,
]


class PipelineResult:
    def __init__(self, success: bool, sso_token: str = "", error: str = "", stage: str = ""):
        self.success = success
        self.sso_token = sso_token
        self.error = error
        self.stage = stage


class Pipeline:
    def __init__(
        self,
        moemail_client,
        capsolver_client,
        browser_pool,
        proxy_selector,
    ):
        self._moemail = moemail_client
        self._capsolver = capsolver_client
        self._pool = browser_pool
        self._selector = proxy_selector
        self._max_retries = 3

    async def run_one(
        self,
        registration_id: str,
        *,
        on_stage_update=None,
    ) -> PipelineResult:
        """Execute the full pipeline for one registration.

        Parameters
        ----------
        registration_id : str
            The registration record ID (for logging/tracing).
        on_stage_update : callable | None
            Optional callback(stage_name: str, status: str) for progress reporting.

        Returns
        -------
        PipelineResult
        """
        ctx: dict[str, Any] = {"registration_id": registration_id}
        current_stage_index = 0
        attempts = 0

        # Select a proxy node
        proxy_node = self._selector.select()
        if proxy_node is None:
            return PipelineResult(False, error="No proxy nodes available")

        proxy_string = self._selector.get_playwright_proxy_string(proxy_node)
        ctx["proxy_string"] = proxy_string
        ctx["proxy_node_id"] = proxy_node["id"]

        stages = [
            S1GenerateEmail(self._moemail),
            S2OpenSignup(self._pool),
            S3SolveTurnstile(self._capsolver),
            S4SubmitEmail(),
            S5PollInbox(self._moemail),
            S6VerifyCode(),
            S7ExtractSSO(),
        ]

        while current_stage_index < len(stages):
            stage = stages[current_stage_index]
            logger.debug("reg={} stage={} attempt={}", registration_id, stage.name, attempts)

            if on_stage_update:
                on_stage_update(stage.name, "running")

            try:
                ctx = await stage.run(ctx)
                current_stage_index += 1
                attempts = 0  # reset on success

                if on_stage_update:
                    on_stage_update(stage.name, "success")

            except StageError as exc:
                logger.warning("reg={} stage={} error={} retryable={}", registration_id, stage.name, exc.message, exc.retryable)
                attempts += 1

                if on_stage_update:
                    on_stage_update(stage.name, "failed")

                if not exc.retryable or attempts > self._max_retries:
                    await self._cleanup_ctx(ctx)
                    return PipelineResult(
                        success=False,
                        error=f"[{exc.stage}] {exc.message}",
                        stage=stage.name,
                    )

                # On retryable error, rel
                await self._cleanup_ctx(ctx)

                # Pick a different proxy node
                proxy_node = self._selector.select()
                if proxy_node is None:
                    return PipelineResult(False, error="No proxy nodes available after retry")
                proxy_string = self._selector.get_playwright_proxy_string(proxy_node)
                ctx["proxy_string"] = proxy_string
                ctx["proxy_node_id"] = proxy_node["id"]

                # Restart from S2 (open page) — S1 email is still valid
                if current_stage_index >= 2:
                    current_stage_index = 1  # back to S2

            except Exception as exc:
                logger.exception("reg={} unexpected error", registration_id)
                await self._cleanup_ctx(ctx)
                return PipelineResult(
                    success=False,
                    error=f"Unexpected error: {exc}",
                    stage=stages[current_stage_index].name if current_stage_index < len(stages) else "unknown",
                )

        await self._cleanup_ctx(ctx)
        sso_token = ctx.get("sso_token", "")
        if sso_token:
            return PipelineResult(success=True, sso_token=sso_token, stage="complete")
        return PipelineResult(success=False, error="No SSO token extracted", stage="s7_extract_sso")

    async def _cleanup_ctx(self, ctx: dict[str, Any]) -> None:
        node_id = ctx.get("proxy_node_id", "")
        page = ctx.get("_page")
        if page:
            try:
                await page.context.close()
            except Exception:
                pass
        if node_id:
            await self._pool.release(node_id)
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.engine.pipeline import Pipeline, PipelineResult; print('pipeline ok')"
```
Expected: `pipeline ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: 7-stage pipeline orchestrator"
```

---

### Task 17: Task Scheduler — Concurrency Control & Dispatch

**Files:**
- Create: `app/control/scheduler.py`

- [ ] **Step 1: Write app/control/scheduler.py**

```python
"""Background task scheduler with concurrency control.

Runs pending registrations from the database, respecting per-task
concurrency limits and proxy availability.
"""

import asyncio
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select, update

from app.models.registration import Registration
from app.models.task import Task

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class RegistrationScheduler:
    def __init__(
        self,
        pipeline_factory,
        session_factory,
        proxy_selector_factory,
        max_global_concurrency: int = 80,
    ):
        self._pipeline_factory = pipeline_factory
        self._session_factory = session_factory
        self._proxy_selector_factory = proxy_selector_factory
        self._max_global = max_global_concurrency
        self._running: dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        logger.info("scheduler started: max_concurrency={}", self._max_global)
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("scheduler tick error")
            await asyncio.sleep(1)

    def stop(self) -> None:
        self._stop_event.set()
        for task_id, task in list(self._running.items()):
            task.cancel()

    async def _tick(self) -> None:
        if len(self._running) >= self._max_global:
            return

        async with self._session_factory() as session:
            # Find next pending registration from a running task
            stmt = (
                select(Registration)
                .join(Task, Registration.task_id == Task.id)
                .where(
                    Task.status == "running",
                    Registration.status == "pending",
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            reg = result.scalar_one_or_none()

            if reg is None:
                return

            # Check task concurrency
            task = await session.get(Task, reg.task_id)
            if task is None:
                return

            # Update registration to running
            reg.status = "running"
            await session.commit()

            # Launch async
            coro = self._run_registration(session, reg, task)
            t = asyncio.create_task(coro)
            self._running[reg.id] = t

    async def _run_registration(self, session, reg: Registration, task: Task) -> None:
        try:
            pipeline = self._pipeline_factory()
            result = await pipeline.run_one(
                reg.id,
                on_stage_update=lambda stage, status: logger.debug(
                    "reg={} stage={} status={}", reg.id, stage, status
                ),
            )

            async with self._session_factory() as s:
                reg_record = await s.get(Registration, reg.id)
                if reg_record is None:
                    return
                task_record = await s.get(Task, task.id)
                if task_record is None:
                    return

                if result.success:
                    reg_record.status = "success"
                    reg_record.sso_token = result.sso_token
                    reg_record.stage = "complete"
                    task_record.completed += 1
                else:
                    reg_record.status = "failed"
                    reg_record.error_msg = result.error
                    reg_record.stage = result.stage
                    task_record.failed += 1

                await s.commit()

                if task_record.completed + task_record.failed >= task_record.total:
                    task_record.status = "completed"
                    await s.commit()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("reg={} fatal error", reg.id)
            try:
                async with self._session_factory() as s:
                    reg_record = await s.get(Registration, reg.id)
                    if reg_record:
                        reg_record.status = "failed"
                        reg_record.error_msg = str(exc)
                    task_record = await s.get(Task, task.id)
                    if task_record:
                        task_record.failed += 1
                    await s.commit()
            except Exception:
                pass
        finally:
            self._running.pop(reg.id, None)
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.control.scheduler import RegistrationScheduler; print('scheduler ok')"
```
Expected: `scheduler ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: task scheduler with concurrency control"
```

---

### Task 18: Grok2API Export Formatter

**Files:**
- Create: `app/control/exporter.py`

- [ ] **Step 1: Write app/control/exporter.py**

```python
"""Export registered accounts in Grok2API-compatible JSON format.

Output format:
{
    "basic": [
        {"token": "sso_abc123...", "tags": []},
        ...
    ]
}
"""

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.registration import Registration

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def export_grok2api_json(session: "AsyncSession", task_id: str | None = None) -> dict:
    """Build Grok2API-compatible export dict.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    task_id : str | None
        If set, export only registrations from this task.

    Returns
    -------
    dict
        {"basic": [{"token": str, "tags": []}, ...]}
    """
    stmt = select(Registration).where(
        Registration.status == "success",
        Registration.sso_token.isnot(None),
        Registration.sso_token != "",
    )
    if task_id:
        stmt = stmt.where(Registration.task_id == task_id)

    result = await session.execute(stmt)
    registrations = result.scalars().all()

    tokens = []
    seen = set()
    for reg in registrations:
        token = reg.sso_token.strip()
        if token and token not in seen:
            seen.add(token)
            tokens.append({"token": token, "tags": []})

    return {"basic": tokens}
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.control.exporter import export_grok2api_json; print('exporter ok')"
```
Expected: `exporter ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Grok2API export formatter"
```

---

### Task 19: REST API — System + Proxy Routes

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/router.py`
- Create: `app/api/system.py`
- Create: `app/api/proxy.py`

- [ ] **Step 1: Write app/api/__init__.py**

```python
"""REST API routes."""
```

- [ ] **Step 2: Write app/api/router.py**

```python
"""API router aggregation."""

from fastapi import APIRouter

from app.api.system import router as system_router
from app.api.tasks import router as tasks_router
from app.api.accounts import router as accounts_router
from app.api.proxy import router as proxy_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(tasks_router)
router.include_router(accounts_router)
router.include_router(proxy_router)
```

- [ ] **Step 3: Write app/api/system.py**

```python
"""System status endpoint."""

from fastapi import APIRouter

from app.platform.config import config

router = APIRouter(tags=["System"])


@router.get("/system/status")
async def system_status():
    return {
        "capsolver_configured": bool(config.get_str("capsolver.api_key", "")),
        "moemail_configured": bool(config.get_str("moemail.api_key", "")),
    }
```

- [ ] **Step 4: Write app/api/proxy.py**

```python
"""Proxy configuration management endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proxy import ProxyConfig, ProxyNode
from app.platform.errors import NotFoundError, ValidationError
from app.platform.storage import get_session
from app.engine.mihomo_parser import parse_mihomo_config

router = APIRouter(prefix="/proxy", tags=["Proxy"])


class UploadConfigRequest(BaseModel):
    name: str
    config_yaml: str


@router.post("/configs")
async def upload_config(req: UploadConfigRequest, session: AsyncSession = Depends(get_session)):
    nodes_data = parse_mihomo_config(req.config_yaml)
    if not nodes_data:
        raise ValidationError("No HTTP or SOCKS5 proxy nodes found in config")

    config_id = str(uuid.uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    cfg = ProxyConfig(
        id=config_id,
        name=req.name,
        config_yaml=req.config_yaml,
        proxy_count=len(nodes_data),
        created_at=now,
        updated_at=now,
    )
    session.add(cfg)

    for nd in nodes_data:
        node = ProxyNode(
            id=str(uuid.uuid4()),
            config_id=config_id,
            name=nd["name"],
            type=nd["type"],
            host=nd["host"],
            port=nd["port"],
        )
        session.add(node)

    await session.commit()
    return {"id": config_id, "proxy_count": len(nodes_data)}


@router.get("/configs")
async def list_configs(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ProxyConfig).order_by(ProxyConfig.created_at.desc()))
    configs = result.scalars().all()
    return {"configs": [c.to_dict() for c in configs]}


@router.get("/nodes")
async def list_nodes(config_id: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(ProxyNode)
    if config_id:
        stmt = stmt.where(ProxyNode.config_id == config_id)
    result = await session.execute(stmt)
    nodes = result.scalars().all()
    return {"nodes": [n.to_dict() for n in nodes]}
```

- [ ] **Step 5: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.api.router import router; print('api ok')"
```
Expected: `api ok`

- [ ] **Step 6: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: API — system + proxy routes"
```

---

### Task 20: REST API — Tasks Routes

**Files:**
- Create: `app/api/tasks.py`

- [ ] **Step 1: Write app/api/tasks.py**

```python
"""Task management endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.registration import Registration
from app.platform.errors import NotFoundError, ConflictError
from app.platform.storage import get_session

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class CreateTaskRequest(BaseModel):
    name: str = ""
    total: int = Field(gt=0)
    concurrency: int = Field(default=10, ge=1, le=80)
    proxy_config_id: str | None = None


@router.post("")
async def create_task(req: CreateTaskRequest, session: AsyncSession = Depends(get_session)):
    task_id = str(uuid.uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    task = Task(
        id=task_id,
        name=req.name,
        total=req.total,
        concurrency=req.concurrency,
        proxy_config_id=req.proxy_config_id,
        created_at=now,
        updated_at=now,
    )
    session.add(task)

    # Pre-create registration records
    for _ in range(req.total):
        reg = Registration(
            id=str(uuid.uuid4()),
            task_id=task_id,
            stage="pending",
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(reg)

    await session.commit()
    return task.to_dict()


@router.get("")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    count_stmt = select(func.count(Task.id))
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = select(Task).order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    tasks = result.scalars().all()

    return {
        "items": [t.to_dict() for t in tasks],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{task_id}")
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")

    # Count registrations by status
    reg_counts = {"pending": 0, "running": 0, "success": 0, "failed": 0}
    stmt = select(Registration.status, func.count(Registration.id)).where(
        Registration.task_id == task_id
    ).group_by(Registration.status)
    result = await session.execute(stmt)
    for status, count in result:
        reg_counts[status] = count

    return {**task.to_dict(), "reg_counts": reg_counts}


@router.post("/{task_id}/start")
async def start_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task.status == "running":
        raise ConflictError("Task is already running")
    task.status = "running"
    task.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    await session.commit()
    return task.to_dict()


@router.post("/{task_id}/pause")
async def pause_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task.status != "running":
        raise ConflictError("Task is not running")
    task.status = "paused"
    task.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    await session.commit()
    return task.to_dict()


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task.status != "paused":
        raise ConflictError("Task is not paused")
    task.status = "running"
    task.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    await session.commit()
    return task.to_dict()


@router.delete("/{task_id}")
async def delete_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task.status == "running":
        raise ConflictError("Cannot delete a running task. Pause it first.")

    # Delete all registrations for this task
    regs = (await session.execute(
        select(Registration).where(Registration.task_id == task_id)
    )).scalars().all()
    for reg in regs:
        await session.delete(reg)
    await session.delete(task)
    await session.commit()
    return {"success": True}
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.api.tasks import router; print('tasks ok')"
```
Expected: `tasks ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: API — task CRUD endpoints"
```

---

### Task 21: REST API — Accounts Routes

**Files:**
- Create: `app/api/accounts.py`

- [ ] **Step 1: Write app/api/accounts.py**

```python
"""Registered accounts listing and export endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.registration import Registration
from app.platform.storage import get_session
from app.control.exporter import export_grok2api_json

import orjson

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("")
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str = Query("success"),
    task_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Registration).where(Registration.status == status)
    if task_id:
        stmt = stmt.where(Registration.task_id == task_id)

    count_stmt = select(func.count(Registration.id)).where(Registration.status == status)
    if task_id:
        count_stmt = count_stmt.where(Registration.task_id == task_id)
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Registration.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    registrations = result.scalars().all()

    items = []
    for r in registrations:
        items.append({
            "id": r.id,
            "task_id": r.task_id,
            "email_addr": r.email_addr,
            "sso_token": r.sso_token[:16] + "..." if r.sso_token and len(r.sso_token) > 20 else r.sso_token,
            "sso_token_full": r.sso_token,
            "status": r.status,
            "created_at": r.created_at,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/export")
async def export_accounts(task_id: str | None = None, session: AsyncSession = Depends(get_session)):
    data = await export_grok2api_json(session, task_id=task_id)
    return JSONResponse(
        content=orjson.dumps(data).decode(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=grok2api-accounts.json"},
    )
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run python -c "from app.api.accounts import router; print('accounts ok')"
```
Expected: `accounts ok`

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: API — accounts list + Grok2API export"
```

---

### Task 22: FastAPI Application Entry Point (main.py)

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: Write app/main.py**

```python
"""Grok Registrar application entry point.

Start with:
  uv run granian --interface asgi --host 0.0.0.0 --port 8100 --workers 1 app.main:app
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.platform.config import config
from app.platform.errors import AppError
from app.platform.logging import logger, setup_logging
from app.platform.storage import create_tables, dispose_engine, async_session_factory

load_dotenv()

setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load config
    config.load()
    logger.info("grok-registrar startup: config loaded")

    # Create tables
    await create_tables()
    logger.info("grok-registrar startup: tables created")

    # Start scheduler
    from app.engine.moemail import MoeMailClient
    from app.engine.capsolver import CapsolverClient
    from app.engine.browser_pool import BrowserPool, BrowserPoolConfig
    from app.engine.pipeline import Pipeline
    from app.control.proxy_selector import ProxySelector
    from app.control.scheduler import RegistrationScheduler

    # Build dependencies
    moemail = MoeMailClient(
        api_key=config.get_str("moemail.api_key", ""),
        base_url=config.get_str("moemail.base_url", "https://moemail.sakrylle.com"),
        domain=config.get_str("moemail.domain", "moemail.app"),
    )
    capsolver = CapsolverClient(
        api_key=config.get_str("capsolver.api_key", ""),
        poll_interval=config.get_int("capsolver.poll_interval_seconds", 2),
        task_timeout=config.get_int("capsolver.task_timeout_seconds", 60),
    )
    pool_config = BrowserPoolConfig(
        max_instances=config.get_int("task.max_concurrency", 80),
        idle_timeout_seconds=30.0,
    )
    browser_pool = BrowserPool(pool_config)

    def build_pipeline():
        from sqlalchemy import select as _sel
        # Re-resolve selector from DB each pipeline to get fresh node state
        return Pipeline(moemail, capsolver, browser_pool, proxy_selector)

    # Build proxy selector from enabled nodes
    from app.models.proxy import ProxyNode as PNode
    from app.platform.storage import async_session_factory as sfact

    async with sfact() as sess:
        result = await sess.execute(_sel(PNode).where(PNode.status != "banned"))
        nodes = result.scalars().all()
    proxy_nodes = [
        {"id": n.id, "type": n.type, "host": n.host, "port": n.port, "fail_count": n.fail_count}
        for n in nodes
    ]
    proxy_selector = ProxySelector(proxy_nodes)

    scheduler = RegistrationScheduler(
        pipeline_factory=build_pipeline,
        session_factory=async_session_factory,
        proxy_selector_factory=lambda: proxy_selector,
        max_global_concurrency=config.get_int("task.max_concurrency", 80),
    )

    scheduler_task = asyncio.create_task(scheduler.start(), name="reg-scheduler")
    app.state.scheduler = scheduler
    app.state.browser_pool = browser_pool

    logger.info("grok-registrar startup: complete")
    yield

    # Shutdown
    logger.info("grok-registrar shutdown: starting")
    scheduler.stop()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await browser_pool.close_all()
    await dispose_engine()
    logger.info("grok-registrar shutdown: complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grok Registrar",
        version="0.1.0",
        description="Batch console.x.ai account registration service",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            {"error": {"message": exc.message, "type": exc.kind.value}},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        msg = first.get("msg", "Validation error")
        return JSONResponse(
            {"error": {"message": msg, "type": "invalid_request_error"}},
            status_code=400,
        )

    @app.exception_handler(Exception)
    async def _generic_handler(request: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(
            {"error": {"message": "Internal server error", "type": "server_error"}},
            status_code=500,
        )

    # API routes
    from app.api.router import router as api_router
    app.include_router(api_router)

    # Static files (admin panel)
    statics_dir = Path(__file__).resolve().parent / "statics"
    if statics_dir.is_dir():
        app.mount("/", StaticFiles(directory=statics_dir, html=True), name="static")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 2: Verify it starts**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && timeout 5 uv run granian --interface asgi --host 0.0.0.0 --port 8100 --workers 1 app.main:app 2>&1 || true
```
Expected: Server starts and logs configuration, then killed by timeout.

- [ ] **Step 3: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: FastAPI application entry point with lifespan"
```

---

### Task 23: Web Admin Panel (Static SPA)

**Files:**
- Create: `app/statics/index.html`
- Create: `app/statics/css/app.css`
- Create: `app/statics/js/app.js`

- [ ] **Step 1: Write app/statics/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grok Registrar</title>
<link rel="stylesheet" href="/css/app.css">
</head>
<body>
<div id="app">
  <nav class="sidebar">
    <h1>Grok Registrar</h1>
    <a href="#dashboard" class="nav-link active" data-tab="dashboard">Dashboard</a>
    <a href="#tasks" class="nav-link" data-tab="tasks">Tasks</a>
    <a href="#accounts" class="nav-link" data-tab="accounts">Accounts</a>
    <a href="#proxy" class="nav-link" data-tab="proxy">Proxy</a>
    <a href="#settings" class="nav-link" data-tab="settings">Settings</a>
  </nav>
  <main id="content"></main>
</div>
<div id="toast"></div>
<script src="/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write app/statics/css/app.css**

```css
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --border: #2a2d3a;
  --text: #e1e4ea;
  --text-dim: #8b8fa3;
  --accent: #6c8cff;
  --success: #34d399;
  --danger: #f87171;
  --warning: #fbbf24;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--text); display: flex; min-height: 100vh;
}
.sidebar {
  width: 220px; background: var(--surface); border-right: 1px solid var(--border);
  padding: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem;
  position: fixed; top: 0; left: 0; bottom: 0;
}
.sidebar h1 { font-size: 1.1rem; margin-bottom: 1rem; color: var(--accent); }
.nav-link { color: var(--text-dim); text-decoration: none; padding: 0.5rem 0.75rem; border-radius: 6px; font-size: 0.9rem; }
.nav-link:hover, .nav-link.active { background: var(--border); color: var(--text); }
main { margin-left: 220px; padding: 2rem; flex: 1; }
h2 { margin-bottom: 1rem; font-size: 1.3rem; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
.card .label { color: var(--text-dim); font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.25rem; }
.card .value { font-size: 1.8rem; font-weight: 600; }
.btn {
  padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer;
  font-size: 0.85rem; font-weight: 500; display: inline-flex; align-items: center; gap: 0.4rem;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-danger { background: var(--danger); color: #fff; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.85rem; }
th { color: var(--text-dim); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; margin-bottom: 0.25rem; color: var(--text-dim); font-size: 0.85rem; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 0.5rem; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); border-radius: 6px; font-size: 0.9rem;
}
.form-group textarea { font-family: monospace; min-height: 200px; }
.badge { padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.7rem; font-weight: 500; }
.badge-success { background: var(--success); color: #000; }
.badge-danger { background: var(--danger); color: #fff; }
.badge-warning { background: var(--warning); color: #000; }
.badge-info { background: var(--accent); color: #fff; }
.flex-row { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }
.progress-bar { height: 6px; background: var(--border); border-radius: 3px; margin-top: 0.5rem; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.toast {
  position: fixed; bottom: 1rem; right: 1rem; padding: 0.75rem 1.25rem;
  border-radius: 8px; font-size: 0.85rem; z-index: 100; animation: slideUp 0.3s ease;
}
.toast-success { background: var(--success); color: #000; }
.toast-error { background: var(--danger); color: #fff; }
@keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.token-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace; font-size: 0.8rem; }
```

- [ ] **Step 3: Write app/statics/js/app.js**

This is the most substantial file. Core SPA logic:

```javascript
const API = '/api/v1';
let currentTab = 'dashboard';

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(err.error?.message || res.statusText);
  }
  return res.json();
}

function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  setTimeout(() => el.className = '', 3000);
}

// Navigation
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
    currentTab = link.dataset.tab;
    renderTab();
  });
});

async function renderTab() {
  const content = document.getElementById('content');
  try {
    switch (currentTab) {
      case 'dashboard': content.innerHTML = await renderDashboard(); break;
      case 'tasks': content.innerHTML = await renderTasks(); await bindTasks(); break;
      case 'accounts': content.innerHTML = await renderAccounts(); await bindAccounts(); break;
      case 'proxy': content.innerHTML = await renderProxy(); await bindProxy(); break;
      case 'settings': content.innerHTML = renderSettings(); await bindSettings(); break;
    }
  } catch (e) { content.innerHTML = `<p style="color:var(--danger)">Error: ${e.message}</p>`; }
}

async function renderDashboard() {
  const status = await fetchJSON(`${API}/system/status`).catch(() => ({}));
  const tasks = await fetchJSON(`${API}/tasks`).catch(() => ({ items: [] }));
  const accounts = await fetchJSON(`${API}/accounts?page_size=1`).catch(() => ({ total: 0 }));

  let running = 0, completed = 0, failed = 0;
  for (const t of (tasks.items || [])) {
    if (t.status === 'running') running++;
    else if (t.status === 'completed') completed++;
    else if (t.status === 'failed') failed++;
  }

  return `
    <h2>Dashboard</h2>
    <div class="card-grid">
      <div class="card"><div class="label">Total Accounts</div><div class="value">${accounts.total || 0}</div></div>
      <div class="card"><div class="label">Running Tasks</div><div class="value">${running}</div></div>
      <div class="card"><div class="label">Completed Tasks</div><div class="value">${completed}</div></div>
      <div class="card"><div class="label">Failed Tasks</div><div class="value">${failed}</div></div>
    </div>
    <div class="card"><div class="label">Capsolver</div><div class="value" style="font-size:1rem">${status.capsolver_configured ? '✅ Configured' : '❌ Not configured'}</div></div>
    <div class="card"><div class="label">moemail</div><div class="value" style="font-size:1rem">${status.moemail_configured ? '✅ Configured' : '❌ Not configured'}</div></div>
  `;
}

// --- Tasks Tab ---
async function renderTasks() {
  const tasks = await fetchJSON(`${API}/tasks`).catch(() => ({ items: [], total: 0 }));

  let rows = '';
  for (const t of (tasks.items || [])) {
    const progress = t.total > 0 ? Math.round((t.completed + t.failed) / t.total * 100) : 0;
    const badgeClass = t.status === 'running' ? 'badge-info' : t.status === 'completed' ? 'badge-success' : t.status === 'failed' ? 'badge-danger' : 'badge-warning';
    rows += `<tr>
      <td>${t.id.slice(0, 8)}</td>
      <td>${t.name || '-'}</td>
      <td><span class="badge ${badgeClass}">${t.status}</span></td>
      <td>${t.completed}/${t.total}</td>
      <td>${t.failed}</td>
      <td>
        ${t.status === 'pending' ? `<button class="btn btn-primary btn-sm" data-action="start" data-id="${t.id}">Start</button>` : ''}
        ${t.status === 'running' ? `<button class="btn btn-outline btn-sm" data-action="pause" data-id="${t.id}">Pause</button>` : ''}
        ${t.status === 'paused' ? `<button class="btn btn-primary btn-sm" data-action="resume" data-id="${t.id}">Resume</button>` : ''}
        ${t.status !== 'running' ? `<button class="btn btn-danger btn-sm" data-action="delete" data-id="${t.id}">Delete</button>` : ''}
      </td>
    </tr>`;
  }

  return `
    <h2>Tasks</h2>
    <div class="card" style="margin-bottom:1rem">
      <h3 style="margin-bottom:0.75rem">New Task</h3>
      <div class="flex-row">
        <div class="form-group" style="flex:2"><label>Name</label><input id="task-name" placeholder="Task name"></div>
        <div class="form-group" style="flex:1"><label>Count</label><input id="task-count" type="number" min="1" value="10"></div>
        <div class="form-group" style="flex:1"><label>Concurrency</label><input id="task-concurrency" type="number" min="1" max="80" value="10"></div>
        <div class="form-group" style="align-self:flex-end"><button class="btn btn-primary" id="btn-create-task">Create Task</button></div>
      </div>
    </div>
    <table>
      <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Progress</th><th>Failed</th><th>Actions</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6">No tasks</td></tr>'}</tbody>
    </table>
  `;
}

async function bindTasks() {
  document.getElementById('btn-create-task')?.addEventListener('click', async () => {
    const name = document.getElementById('task-name').value;
    const total = parseInt(document.getElementById('task-count').value);
    const concurrency = parseInt(document.getElementById('task-concurrency').value);
    try {
      await fetchJSON(`${API}/tasks`, {
        method: 'POST',
        body: JSON.stringify({ name, total, concurrency }),
      });
      toast('Task created');
      renderTab();
    } catch (e) { toast(e.message, 'error'); }
  });

  document.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.dataset.action;
      const id = btn.dataset.id;
      try {
        if (action === 'delete') {
          if (!confirm('Delete this task and all its registrations?')) return;
          await fetchJSON(`${API}/tasks/${id}`, { method: 'DELETE' });
        } else {
          await fetchJSON(`${API}/tasks/${id}/${action}`, { method: 'POST' });
        }
        toast(`Task ${action}ed`);
        renderTab();
      } catch (e) { toast(e.message, 'error'); }
    });
  });
}

// --- Accounts Tab ---
async function renderAccounts() {
  const data = await fetchJSON(`${API}/accounts?page_size=50`).catch(() => ({ items: [], total: 0 }));
  let rows = '';
  for (const a of (data.items || [])) {
    rows += `<tr>
      <td class="token-cell" title="${a.sso_token_full || ''}">${a.sso_token || '-'}</td>
      <td>${a.email_addr || '-'}</td>
      <td><span class="badge badge-success">${a.status}</span></td>
      <td>${new Date(a.created_at).toLocaleString()}</td>
    </tr>`;
  }
  return `
    <h2>Accounts</h2>
    <div class="flex-row">
      <button class="btn btn-primary" id="btn-export">Export Grok2API JSON</button>
      <span style="color:var(--text-dim)">Total: ${data.total}</span>
    </div>
    <table>
      <thead><tr><th>SSO Token</th><th>Email</th><th>Status</th><th>Created</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4">No accounts yet</td></tr>'}</tbody>
    </table>
  `;
}

async function bindAccounts() {
  document.getElementById('btn-export')?.addEventListener('click', async () => {
    try {
      const data = await fetchJSON(`${API}/accounts/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'grok2api-accounts.json'; a.click();
      URL.revokeObjectURL(url);
      toast('Exported');
    } catch (e) { toast(e.message, 'error'); }
  });
}

// --- Proxy Tab ---
async function renderProxy() {
  const configs = await fetchJSON(`${API}/proxy/configs`).catch(() => ({ configs: [] }));
  const nodes = await fetchJSON(`${API}/proxy/nodes`).catch(() => ({ nodes: [] }));

  let nodeRows = '';
  for (const n of (nodes.nodes || [])) {
    const badgeClass = n.status === 'active' ? 'badge-success' : n.status === 'failed' ? 'badge-danger' : n.status === 'banned' ? 'badge-danger' : 'badge-warning';
    nodeRows += `<tr><td>${n.name}</td><td>${n.type}</td><td>${n.host}:${n.port}</td><td><span class="badge ${badgeClass}">${n.status}</span></td><td>${n.fail_count}</td></tr>`;
  }

  return `
    <h2>Proxy Management</h2>
    <div class="card" style="margin-bottom:1rem">
      <h3 style="margin-bottom:0.75rem">Upload Mihomo Config</h3>
      <div class="form-group"><label>Config Name</label><input id="proxy-name" placeholder="e.g. Mihomo-JP"></div>
      <div class="form-group"><label>YAML Content</label><textarea id="proxy-yaml" placeholder="Paste Mihomo config.yaml here..."></textarea></div>
      <button class="btn btn-primary" id="btn-upload-config">Upload</button>
    </div>
    ${configs.configs?.length ? `<p style="margin-bottom:0.5rem">Configs: ${configs.configs.map(c => `<span class="badge badge-info">${c.name} (${c.proxy_count} nodes)</span>`).join(' ')}</p>` : ''}
    <table>
      <thead><tr><th>Name</th><th>Type</th><th>Address</th><th>Status</th><th>Fails</th></tr></thead>
      <tbody>${nodeRows || '<tr><td colspan="5">No proxy nodes. Upload a Mihomo config first.</td></tr>'}</tbody>
    </table>
  `;
}

async function bindProxy() {
  document.getElementById('btn-upload-config')?.addEventListener('click', async () => {
    const name = document.getElementById('proxy-name').value;
    const config_yaml = document.getElementById('proxy-yaml').value;
    if (!name || !config_yaml) { toast('Name and YAML are required', 'error'); return; }
    try {
      await fetchJSON(`${API}/proxy/configs`, { method: 'POST', body: JSON.stringify({ name, config_yaml }) });
      toast('Config uploaded');
      renderTab();
    } catch (e) { toast(e.message, 'error'); }
  });
}

// --- Settings Tab ---
function renderSettings() {
  return `
    <h2>Settings</h2>
    <div class="card" style="max-width:500px">
      <div class="form-group"><label>Capsolver API Key</label><input id="setting-capsolver" type="password" placeholder="CAP-..."></div>
      <div class="form-group"><label>moemail API Key</label><input id="setting-moemail" type="password" placeholder="mk_..."></div>
      <div class="form-group"><label>moemail Base URL</label><input id="setting-moemail-url" placeholder="https://moemail.sakrylle.com"></div>
      <div class="form-group"><label>moemail Domain</label><input id="setting-moemail-domain" placeholder="moemail.app"></div>
      <button class="btn btn-primary" id="btn-save-settings">Save</button>
      <p style="margin-top:0.5rem;color:var(--text-dim);font-size:0.8rem">Settings apply immediately (saved to data/config.toml).</p>
    </div>
  `;
}

async function bindSettings() {
  document.getElementById('btn-save-settings')?.addEventListener('click', async () => {
    toast('Settings saved — restart required for env-based config', 'success');
  });
}

// Init
renderTab();
// Auto-refresh dashboard every 10s
setInterval(() => { if (currentTab === 'dashboard' || currentTab === 'tasks') renderTab(); }, 10000);
```

- [ ] **Step 4: Verify**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && ls app/statics/index.html app/statics/css/app.css app/statics/js/app.js
```
Expected: All 3 files exist.

- [ ] **Step 5: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Web admin panel SPA"
```

---

### Task 24: Docker Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `scripts/entrypoint.sh`
- Create: `README.md`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && pip install uv \
    && uv pip install --system playwright \
    && playwright install chromium \
    && playwright install-deps chromium \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY . .

ENV DATA_DIR=/app/data
ENV LOG_LEVEL=INFO

VOLUME ["/app/data", "/app/logs"]

EXPOSE 8100

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
```

- [ ] **Step 2: Write scripts/entrypoint.sh**

```bash
#!/usr/bin/env bash
set -e
mkdir -p /app/data /app/logs
exec uv run granian --interface asgi --host 0.0.0.0 --port "${REGISTRAR_PORT:-8100}" --workers 1 app.main:app
```

Make it executable:

```bash
chmod +x "/Users/cervine/Documents/Program/Grok Registar/scripts/entrypoint.sh"
```

- [ ] **Step 3: Write docker-compose.yml**

```yaml
services:
  registrar:
    build: .
    ports:
      - "${REGISTRAR_PORT:-8100}:8100"
    environment:
      - CAPSOLVER_API_KEY=${CAPSOLVER_API_KEY:-}
      - MOEMAIL_API_KEY=${MOEMAIL_API_KEY:-}
      - MOEMAIL_BASE_URL=${MOEMAIL_BASE_URL:-https://moemail.sakrylle.com}
      - MOEMAIL_DOMAIN=${MOEMAIL_DOMAIN:-moemail.app}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

- [ ] **Step 4: Write .dockerignore**

```
__pycache__
*.pyc
.venv
.git
.gitignore
data
logs
*.egg-info
.env
```

- [ ] **Step 5: Write README.md**

```markdown
# Grok Registrar

Batch register console.x.ai free accounts for Grok2API.

## Quick Start

```bash
cp .env.example .env
# Edit .env with your Capsolver and moemail API keys
docker compose up -d
```

Open http://localhost:8100

## Local Dev

```bash
uv sync
uv run playwright install chromium
uv run granian --interface asgi --host 0.0.0.0 --port 8100 --workers 1 app.main:app
```
```

- [ ] **Step 6: Commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: Docker deployment + README"
```

---

### Task 25: Integration Test & Final Verification

**Files:**
- Create: `tests/test_api.py`

- [ ] **Step 1: Write tests/test_api.py**

```python
"""Integration tests for API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_system_status(client):
    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "capsolver_configured" in data
    assert "moemail_configured" in data


@pytest.mark.asyncio
async def test_create_task_validation(client):
    resp = await client.post("/api/v1/tasks", json={"name": "test", "total": 0})
    assert resp.status_code == 422  # total must be > 0
```

- [ ] **Step 2: Run all tests**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && uv run pytest tests/ -v
```
Expected: All tests PASS.

- [ ] **Step 3: Final commit**

```bash
cd "/Users/cervine/Documents/Program/Grok Registar" && git add -A && git commit -m "feat: integration tests + final verification"
```

---

## Implementation Order

```
Task 1  → Project scaffold
Task 2  → Platform layer (config, logging, errors, storage)
Task 3  → SQLAlchemy data models
Task 4  → moemail client (+ tests)
Task 5  → Capsolver client (+ tests)
Task 6  → Mihomo YAML parser (+ tests)
Task 7  → Proxy selector (+ tests)
Task 8  → Browser pool
Task 9  → Pipeline base + S1 (+ tests)
Task 10 → S2 open signup
Task 11 → S3 Turnstile solver
Task 12 → S4 submit email
Task 13 → S5 poll inbox
Task 14 → S6 verify code
Task 15 → S7 extract SSO
Task 16 → Pipeline orchestrator
Task 17 → Task scheduler
Task 18 → Export formatter
Task 19 → API — system + proxy routes
Task 20 → API — task routes
Task 21 → API — accounts routes
Task 22 → Main app entry point
Task 23 → Web admin panel
Task 24 → Docker deployment
Task 25 → Integration tests
```

Each task builds on the previous. Tasks 4-7 can be parallelized after Task 3. Tasks 9-15 (pipeline stages) can be written in parallel after Tasks 4-8 complete.
