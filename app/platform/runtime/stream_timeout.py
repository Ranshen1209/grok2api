"""Idle + total timeout guard for upstream streaming iterators.

curl_cffi's ``stream=True`` mode only installs a *low-speed* timeout
(``LOW_SPEED_LIMIT=1`` byte/s over ``LOW_SPEED_TIME`` seconds) and no absolute
``CURLOPT_TIMEOUT`` — so an upstream that holds the socket open with a slow
trickle but never sends a terminal frame can keep a non-stream aggregation
request alive indefinitely, occupying a concurrency slot until the downstream
client gives up. This wrapper adds an application-level guard:

* **idle**  — abort if no item arrives within ``idle_s`` seconds (the strict
  "no bytes for N seconds" signal; ``0`` disables).
* **total** — abort if the whole iteration exceeds ``total_s`` seconds, an
  absolute backstop curl lacks in stream mode (``0`` disables).

On breach it raises :class:`UpstreamTimeoutError` (retryable). A normal end of
stream (``StopAsyncIteration``) returns cleanly, and any other exception from
the source propagates unchanged so a genuine mid-stream abort stays an error.
The underlying source is always ``aclose()``d on exit.
"""

import asyncio
from typing import AsyncIterator, TypeVar

from app.platform.errors import UpstreamTimeoutError

T = TypeVar("T")


async def aiter_with_timeout(
    source: AsyncIterator[T],
    *,
    idle_s: float,
    total_s: float = 0.0,
) -> AsyncIterator[T]:
    """Yield from *source*, enforcing idle and total timeouts.

    Args:
        source: an async iterator/generator of upstream lines or events.
        idle_s: max seconds allowed between consecutive items (``0`` disables).
        total_s: absolute cap from the first pull (``0`` disables).
    """
    agen = source.__aiter__()
    loop = asyncio.get_event_loop()
    start = loop.time()
    try:
        while True:
            step: float | None = idle_s if idle_s and idle_s > 0 else None

            if total_s and total_s > 0:
                remaining = total_s - (loop.time() - start)
                if remaining <= 0:
                    raise UpstreamTimeoutError(
                        f"Upstream exceeded total timeout {total_s}s "
                        "without terminal response",
                        kind="total",
                        timeout_s=total_s,
                    )
                step = remaining if step is None else min(step, remaining)

            try:
                if step is None:
                    item = await agen.__anext__()
                else:
                    item = await asyncio.wait_for(agen.__anext__(), timeout=step)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                elapsed = loop.time() - start
                if total_s and total_s > 0 and elapsed >= total_s:
                    raise UpstreamTimeoutError(
                        f"Upstream exceeded total timeout {total_s}s "
                        "without terminal response",
                        kind="total",
                        timeout_s=total_s,
                    ) from None
                raise UpstreamTimeoutError(
                    f"Upstream idle for {idle_s}s without data",
                    kind="idle",
                    timeout_s=idle_s,
                ) from None

            yield item
    finally:
        aclose = getattr(agen, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass


__all__ = ["aiter_with_timeout"]
