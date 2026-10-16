"""Rerun the auto-cap scenario and log when each server request starts/ends."""
import asyncio, os, sys, time, threading
sys.path.insert(0, "/home/rswargo/adaptiSeq")
import tests.servers as S
from adaptiseq.options import Options
from adaptiseq.engine.seam import SegmentedEngine
from adaptiseq.batch import BatchDownloader, DownloadTask

ev, lock, t0 = [], threading.Lock(), [0.0]
orig = S._MultiHandler.do_GET
def logged(self):
    a = time.monotonic() - t0[0]
    try:
        orig(self)
    finally:
        with lock:
            ev.append((a, time.monotonic() - t0[0], self.path, self.headers.get("Range")))
S._MultiHandler.do_GET = logged

delay = float(sys.argv[1]); tmp = sys.argv[2]
files = {f"g{i}.bin": os.urandom(8 * 1024 * 1024) for i in range(4)}
with S.MultiFileRangeServer(files, delay=delay) as srv:
    opts = Options(engine="segmented", segment_size=1024 * 1024, max_segments=4,
                   quiet=True, adaptive=False, jobs=4)
    eng = SegmentedEngine(opts, tmp)
    tasks = [DownloadTask(srv.url(n), n, "ACC") for n in files]
    t0[0] = time.monotonic()
    failed = asyncio.run(BatchDownloader(eng, opts, tmp).run(tasks))
    print(f"peak={srv.max_concurrent} failed={len(failed)} total={time.monotonic()-t0[0]:.2f}s")
    if srv.max_concurrent <= 8:
        for a, b, p, r in sorted(ev):
            print(f"  {a:6.3f}-{b:6.3f} {p} {r}")
