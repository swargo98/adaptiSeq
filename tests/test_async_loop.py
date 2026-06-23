"""Regression: the public API must work when an asyncio loop is already running.

Jupyter / Google Colab / IPython run an event loop in the kernel thread, so a
bare ``asyncio.run()`` inside :func:`adaptiseq.fetch` raises "asyncio.run()
cannot be called from a running event loop". :func:`adaptiseq._async.run_sync`
falls back to a worker thread in that case. These tests cover the fallback with a
trivial coroutine (no network), so they run offline.
"""

from __future__ import annotations

import asyncio

from adaptiseq._async import run_sync


async def _answer() -> int:
    await asyncio.sleep(0)
    return 42


def test_run_sync_without_running_loop() -> None:
    # No loop running: the normal asyncio.run path.
    assert run_sync(_answer()) == 42


def test_run_sync_inside_running_loop() -> None:
    # A loop IS running (the Colab/Jupyter case): must not raise, must return.
    async def driver() -> int:
        # calling the *sync* helper from within a running loop is the trap
        return run_sync(_answer())

    assert asyncio.run(driver()) == 42


def test_run_sync_drives_reentrant_loop_directly(monkeypatch) -> None:
    # When the running loop is marked re-entrant by nest_asyncio, run_sync must
    # call loop.run_until_complete directly (a worker thread would deadlock).
    calls = {}

    class FakeReentrantLoop:
        _nest_patched = True

        def run_until_complete(self, coro):
            coro.close()  # we only assert the routing; don't actually run it
            calls["used"] = True
            return 99

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeReentrantLoop())
    assert run_sync(_answer()) == 99
    assert calls.get("used") is True
