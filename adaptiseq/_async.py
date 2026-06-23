"""Run an ``asyncio`` coroutine to completion from synchronous code.

``asyncio.run`` raises ``RuntimeError: asyncio.run() cannot be called from a
running event loop`` when a loop is already running in the current thread — which
is exactly the case inside Jupyter / Google Colab / IPython and any other async
host. The public API (:func:`adaptiseq.fetch`) is documented as usable from "a
script, notebook, or pipeline", so it must work there.

:func:`run_sync` uses the normal :func:`asyncio.run` when no loop is running, and
otherwise runs the coroutine in a dedicated worker thread that owns its own event
loop (so every aiohttp session/connector is created and used on that one loop).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_sync(coro: "Coroutine[Any, Any, T]") -> T:
    """Block until ``coro`` finishes and return its result, loop or no loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running in this thread: the normal, fast path.
        return asyncio.run(coro)
    # A loop is already running here (notebook / async host). We cannot nest
    # asyncio.run, so run the coroutine in a separate thread with its own loop
    # and wait for it. The coroutine has not been awaited yet, so it is safe to
    # hand to another thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()
