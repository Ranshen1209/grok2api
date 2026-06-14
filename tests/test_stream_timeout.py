"""Tests for the non-stream upstream timeout guard.

Covers the four upstream behaviours the guard must distinguish (mirrors the
brief's verification matrix), plus retry/feedback integration:

  (a) normal completion (terminal frame present)  -> yield all, clean stop
  (b) clean EOF without terminal frame             -> yield all, clean stop
  (c) idle gap (N seconds with zero bytes)         -> raise retryable timeout
  (d) mid-stream abort (TCP drop / upstream error) -> propagate original error
  (e) trickle that never terminates                -> total cap raises timeout

The unit under test is ``aiter_with_timeout`` — a reusable wrapper around an
async upstream line/event iterator — together with the retry predicate and
account-feedback mapping that route its timeout error.
"""

import asyncio
import unittest

from app.platform.errors import UpstreamError, UpstreamTimeoutError
from app.platform.runtime.stream_timeout import aiter_with_timeout
from app.control.account.enums import FeedbackKind
from app.control.account.invalid_credentials import feedback_kind_for_error
from app.products.openai.chat import _should_retry_upstream


async def _drain(source, **kwargs):
    out = []
    async for item in aiter_with_timeout(source, **kwargs):
        out.append(item)
    return out


class _TrackingSource:
    """Async generator wrapper that records whether cleanup (aclose) ran."""

    def __init__(self, gen):
        self._gen = gen
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._gen.__anext__()

    async def aclose(self):
        self.closed = True
        await self._gen.aclose()


class AiterWithTimeoutTest(unittest.TestCase):
    # ── (a) + (b) normal / clean-EOF completion ──────────────────────────
    def test_normal_completion_yields_all_then_stops(self):
        async def src():
            for i in range(3):
                yield f"line{i}"

        out = asyncio.run(_drain(src(), idle_s=1.0, total_s=5.0))
        self.assertEqual(out, ["line0", "line1", "line2"])

    def test_clean_eof_without_terminal_returns(self):
        # Upstream simply ends (no [DONE]/finalMetadata). Must not raise.
        async def src():
            yield "partial"
            # ends here — EOF without any terminal marker

        out = asyncio.run(_drain(src(), idle_s=1.0, total_s=5.0))
        self.assertEqual(out, ["partial"])

    # ── (c) idle gap -> retryable timeout ────────────────────────────────
    def test_idle_gap_raises_retryable_timeout(self):
        async def src():
            yield "first"
            await asyncio.sleep(0.3)  # > idle_s: simulate wedged upstream
            yield "never"

        async def run():
            return await _drain(src(), idle_s=0.05, total_s=5.0)

        with self.assertRaises(UpstreamTimeoutError) as ctx:
            asyncio.run(run())
        self.assertEqual(ctx.exception.timeout_kind, "idle")

    def test_idle_timeout_before_first_byte(self):
        # Wedged before any data arrives at all.
        async def src():
            await asyncio.sleep(0.3)
            yield "never"

        with self.assertRaises(UpstreamTimeoutError) as ctx:
            asyncio.run(_drain(src(), idle_s=0.05, total_s=5.0))
        self.assertEqual(ctx.exception.timeout_kind, "idle")

    # ── (d) mid-stream abort -> propagate original error, not timeout ────
    def test_midstream_error_propagates_unchanged(self):
        sentinel = UpstreamError("connection reset", status=502)

        async def src():
            yield "first"
            raise sentinel

        with self.assertRaises(UpstreamError) as ctx:
            asyncio.run(_drain(src(), idle_s=1.0, total_s=5.0))
        self.assertIs(ctx.exception, sentinel)
        self.assertNotIsInstance(ctx.exception, UpstreamTimeoutError)

    # ── (e) trickle defeats idle but total cap fires ─────────────────────
    def test_total_cap_raises_when_trickle_never_terminates(self):
        async def src():
            while True:
                await asyncio.sleep(0.02)  # keeps idle timer from tripping
                yield ":keepalive"

        with self.assertRaises(UpstreamTimeoutError) as ctx:
            asyncio.run(_drain(src(), idle_s=10.0, total_s=0.2))
        self.assertEqual(ctx.exception.timeout_kind, "total")

    # ── cleanup: underlying source is always closed ──────────────────────
    def test_source_closed_on_timeout(self):
        async def gen():
            yield "first"
            await asyncio.sleep(0.3)
            yield "never"

        src = _TrackingSource(gen())
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(_drain(src, idle_s=0.05, total_s=5.0))
        self.assertTrue(src.closed, "source must be aclose()d on timeout")

    def test_source_closed_on_normal_completion(self):
        async def gen():
            yield "only"

        src = _TrackingSource(gen())
        asyncio.run(_drain(src, idle_s=1.0, total_s=5.0))
        self.assertTrue(src.closed, "source must be aclose()d on clean stop")

    # ── disabled guards (0 == off) ───────────────────────────────────────
    def test_zero_idle_disables_idle_check(self):
        async def src():
            yield "a"
            await asyncio.sleep(0.15)  # would trip a small idle, but idle off
            yield "b"

        out = asyncio.run(_drain(src(), idle_s=0.0, total_s=0.0))
        self.assertEqual(out, ["a", "b"])


class TimeoutErrorIntegrationTest(unittest.TestCase):
    def test_timeout_error_is_retryable_even_when_504_not_in_codes(self):
        exc = UpstreamTimeoutError("idle", kind="idle", timeout_s=45.0)
        # default retry codes are {429,401,503} — 504 is NOT among them,
        # yet a timeout must still trigger an account switch.
        self.assertTrue(_should_retry_upstream(exc, frozenset({429, 401, 503})))

    def test_timeout_error_does_not_expire_account(self):
        exc = UpstreamTimeoutError("idle", kind="idle", timeout_s=45.0)
        # A slow upstream is not a credential problem: must map to a health
        # signal, never UNAUTHORIZED/expiry.
        self.assertEqual(feedback_kind_for_error(exc), FeedbackKind.SERVER_ERROR)

    def test_timeout_error_status_is_504(self):
        exc = UpstreamTimeoutError("idle", kind="idle", timeout_s=45.0)
        self.assertEqual(exc.status, 504)
        self.assertIsInstance(exc, UpstreamError)


class _FakeAcct:
    def __init__(self, token):
        self.token = token


class _FakeDirectory:
    """Minimal account directory: records feedback, no-op release."""

    def __init__(self):
        self.feedbacks = []

    async def release(self, acct):
        return None

    async def feedback(self, token, kind, mode_id, *, now_s_val=None):
        self.feedbacks.append((token, kind, mode_id))


class _FakeSpec:
    def is_console_chat(self):
        return False


async def _wedged_lines():
    """Upstream that sends one frame then wedges forever (no terminal)."""
    yield 'data: {"result":{"response":{"token":"hi","messageTag":"final"}}}'
    await asyncio.sleep(3600)
    yield "never"


async def _wedged_console_events():
    yield ("response.output_text.delta", '{"delta":"hi"}')
    await asyncio.sleep(3600)
    yield ("response.completed", "{}")


class NonStreamWiringTest(unittest.IsolatedAsyncioTestCase):
    """The non-stream aggregation paths must fail fast on a wedged upstream
    instead of hanging until the client socket times out.
    """

    def setUp(self):
        from app.platform.config.snapshot import config
        self._cfg = config
        self._saved_data = config._data
        self._saved_loaded = config._loaded
        # Strict, tiny idle so the test resolves quickly.
        config._data = {"chat": {"idle_timeout": 0.05, "total_timeout": 0.0}}
        config._loaded = True

    def tearDown(self):
        self._cfg._data = self._saved_data
        self._cfg._loaded = self._saved_loaded

    async def test_chat_nonstream_raises_timeout_not_hang(self):
        import app.dataplane.account as account_mod
        from app.products.openai import chat as chat_mod
        from unittest import mock

        saved_dir = account_mod._directory
        account_mod._directory = _FakeDirectory()
        try:
            with mock.patch.object(chat_mod, "resolve_model", lambda m: _FakeSpec()), \
                 mock.patch.object(chat_mod, "selection_max_retries", lambda: 0), \
                 mock.patch.object(
                     chat_mod, "reserve_account",
                     mock.AsyncMock(return_value=(_FakeAcct("tok-a"), 1)),
                 ), \
                 mock.patch.object(
                     chat_mod, "_stream_chat", lambda **kw: _wedged_lines(),
                 ):
                with self.assertRaises(UpstreamTimeoutError):
                    await asyncio.wait_for(
                        chat_mod.completions(
                            model="grok-x",
                            messages=[{"role": "user", "content": "hello"}],
                            stream=False,
                        ),
                        timeout=2.0,
                    )
        finally:
            account_mod._directory = saved_dir

    async def test_console_nonstream_raises_timeout_not_hang(self):
        import app.dataplane.account as account_mod
        from app.products.openai import console_chat as console_mod
        from unittest import mock

        saved_dir = account_mod._directory
        account_mod._directory = _FakeDirectory()
        try:
            with mock.patch.object(console_mod, "resolve_model", lambda m: _FakeSpec()), \
                 mock.patch.object(console_mod, "selection_max_retries", lambda: 0), \
                 mock.patch.object(
                     console_mod, "reserve_account",
                     mock.AsyncMock(return_value=(_FakeAcct("tok-a"), 5)),
                 ), \
                 mock.patch.object(
                     console_mod, "stream_console_chat",
                     lambda *a, **kw: _wedged_console_events(),
                 ):
                with self.assertRaises(UpstreamTimeoutError):
                    await asyncio.wait_for(
                        console_mod.completions(
                            model="grok-4.3-console",
                            messages=[{"role": "user", "content": "hello"}],
                            stream=False,
                        ),
                        timeout=2.0,
                    )
        finally:
            account_mod._directory = saved_dir


async def _stream_lines_with_terminal():
    yield 'data: {"result":{"response":{"token":"Hello","messageTag":"final"}}}'
    yield 'data: {"result":{"response":{"finalMetadata":{"followUpSuggestions":[]}}}}'


async def _stream_lines_no_terminal():
    # Upstream EOFs after content, never sending finalMetadata / [DONE].
    yield 'data: {"result":{"response":{"token":"Hello","messageTag":"final"}}}'


class StreamingNoRegressionTest(unittest.IsolatedAsyncioTestCase):
    """The stream=true path must keep forwarding chunks and always cap the SSE
    with a terminal [DONE], including when the upstream omits its own terminal
    frame (brief item #2). Streaming code is untouched by this change; these
    lock that baseline.
    """

    def setUp(self):
        from app.platform.config.snapshot import config
        self._cfg = config
        self._saved_data = config._data
        self._saved_loaded = config._loaded
        config._data = {"chat": {"idle_timeout": 0.0, "total_timeout": 0.0}}
        config._loaded = True

    def tearDown(self):
        self._cfg._data = self._saved_data
        self._cfg._loaded = self._saved_loaded

    async def _collect(self, line_factory):
        import app.dataplane.account as account_mod
        from app.products.openai import chat as chat_mod
        from unittest import mock

        saved_dir = account_mod._directory
        account_mod._directory = _FakeDirectory()
        try:
            with mock.patch.object(chat_mod, "resolve_model", lambda m: _FakeSpec()), \
                 mock.patch.object(chat_mod, "selection_max_retries", lambda: 0), \
                 mock.patch.object(
                     chat_mod, "reserve_account",
                     mock.AsyncMock(return_value=(_FakeAcct("tok-a"), 1)),
                 ), \
                 mock.patch.object(
                     chat_mod, "_stream_chat", lambda **kw: line_factory(),
                 ):
                gen = await chat_mod.completions(
                    model="grok-x",
                    messages=[{"role": "user", "content": "hi"}],
                    stream=True,
                    emit_think=False,
                )
                chunks = []
                async for chunk in gen:
                    chunks.append(chunk)
                return "".join(chunks)
        finally:
            account_mod._directory = saved_dir

    async def test_stream_forwards_content_and_terminates(self):
        out = await self._collect(_stream_lines_with_terminal)
        self.assertIn("Hello", out)
        self.assertTrue(out.rstrip().endswith("data: [DONE]"))

    async def test_stream_eof_without_terminal_still_emits_done(self):
        out = await self._collect(_stream_lines_no_terminal)
        self.assertIn("Hello", out)
        self.assertTrue(out.rstrip().endswith("data: [DONE]"))


if __name__ == "__main__":
    unittest.main()
