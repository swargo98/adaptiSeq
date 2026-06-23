"""Run an ``asyncio`` coroutine to completion from synchronous code.

``asyncio.run`` raises ``RuntimeError: asyncio.run() cannot be called from a
running event loop`` when a loop is already running in the current thread — the
case inside Jupyter / Google Colab / IPython and any other async host. The public
API (:func:`adaptiseq.fetch`) is documented as usable from "a script, notebook,
or pipeline", so it must work there.

:func:`run_sync` covers three situations:

1. **No loop running** — the normal path: :func:`asyncio.run`.
2. **A loop is running and has been made re-entrant by ``nest_asyncio``** — drive
   the coroutine on that loop directly (spawning a worker thread instead would
   deadlock, because ``nest_asyncio`` patches *all* loops to re-enter the main
   one).
3. **A plain running loop (e.g. Jupyter without ``nest_asyncio``)** — run the
   coroutine in a dedicated worker thread that owns its own event loop, so every
   aiohttp session/connector is created and used on that one loop.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_sync(coro: "Coroutine[Any, Any, T]") -> T:
    """Block until ``coro`` finishes and return its result, loop or no loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running in this thread: the normal, fast path.
        return asyncio.run(coro)

    # A loop is already running in this thread.
    if getattr(loop, "_nest_patched", False):
        # nest_asyncio has made this loop re-entrant — running the coroutine in a
        # separate thread would deadlock (its "fresh" loop is patched to re-enter
        # this one), so drive it directly on the running loop.
        return loop.run_until_complete(coro)

    # Plain running loop (notebook / async host without nest_asyncio): run the
    # coroutine in a worker thread with its own loop and wait for it. The
    # coroutine has not been awaited yet, so it is safe to hand to another thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()
