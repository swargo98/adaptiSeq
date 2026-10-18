"""Why is adaptiSeq slower than kingfisher and iSeq on panel 3b, and where do its
md5 mismatches come from?

Full run rep 3 (job 54927009), panel 3b (8 runs, 16 files of 1.3 to 2.0 GB): the
two adaptiSeq arms (segmented HTTPS from ftp.sra.ebi.ac.uk:443) had 13 md5
mismatches in about 45 file downloads and ended 7/8; the four FTP arms had 0.
The earlier diagnostic (diag_corrupt, 54917324) fetched one file at a time and
saw 16/16 good copies, so the mismatches need the batch's load to show up.

This replays panel 3b's download phase several times, each pass with one method,
all 16 files at once, and checks every file against ENA's md5:

* ``aseq-https``: adaptiSeq's BatchDownloader, fixed 16 workers, segmented HTTPS
  (what the benchmark arms do in phase A);
* ``aseq-ftp``:   the same, but segmented FTP (``protocol="ftp"``);
* ``curl-ftp``:   16 plain curl FTP streams, one per file (what iSeq/fastq-dl do);
* ``curl-https``: 16 plain curl HTTPS streams, one per file.

For each pass it logs wall time, per-file time and rate, the HostGuard trips
(refused connects halve the per-host cap), every HTTPS response's headers, and
the server address. A mismatching copy is kept and compared 1 MiB block by block
with a good copy of the same file: bad blocks at segment boundaries, or zeros,
point at adaptiSeq; scattered garbage inside a segment points at the server or
the path; a bad copy from curl clears adaptiSeq.

Usage (from plans_and_experiments/, see diag_batch.sbatch):
    python -u diag_batch/diag_batch.py --out DIR --work DIR --rounds 2 \
        NAME=MD5=SIZE=FTP_PATH ...
"""

import argparse
import asyncio
import functools
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)

import aiohttp  # noqa: E402

import adaptiseq.batch as aseq_batch  # noqa: E402
from adaptiseq.batch import BatchDownloader, DownloadTask  # noqa: E402
from adaptiseq.engine.ratelimit import HostGuard  # noqa: E402
from adaptiseq.engine.seam import SegmentedEngine  # noqa: E402
from adaptiseq.engine.segmented import calculate_segments  # noqa: E402
from adaptiseq.options import Options  # noqa: E402

BLOCK = 1024 * 1024
MAX_BAD_KEPT = 12


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 * BLOCK), b""):
            h.update(b)
    return h.hexdigest()


def compare(bad, good):
    """Summary of the 1 MiB blocks of ``bad`` that differ from ``good``."""
    diff, zero, first_byte = [], 0, None
    with open(bad, "rb") as fb, open(good, "rb") as fg:
        i = 0
        while True:
            b, g = fb.read(BLOCK), fg.read(BLOCK)
            if not b and not g:
                break
            if b != g:
                diff.append(i)
                if b and b.strip(b"\0") == b"":
                    zero += 1
                if first_byte is None:
                    n = min(len(b), len(g))
                    k = next((k for k in range(n) if b[k] != g[k]), n)
                    first_byte = i * BLOCK + k
            i += 1
    if not diff:
        return {"differing_blocks": 0}
    runs, start, prev = [], diff[0], diff[0]
    for x in diff[1:]:
        if x != prev + 1:
            runs.append((start, prev))
            start = x
        prev = x
    runs.append((start, prev))
    return {"differing_blocks": len(diff), "zero_blocks": zero, "first_byte": first_byte,
            "block_runs_MiB": runs[:50], "n_runs": len(runs),
            "size_bad": os.path.getsize(bad), "size_good": os.path.getsize(good)}


class RecordingGuard(HostGuard):
    """HostGuard that also remembers the lowest cap it fell to."""

    instances = []

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.min_cap_seen = self.default_cap
        RecordingGuard.instances.append(self)

    async def note_pushback(self, host, kind="pushback"):
        await super().note_pushback(host, kind)
        self.min_cap_seen = min(self.min_cap_seen, self.cap_of(host))


def make_session_factory(hdr_log, method, rnd):
    real = aiohttp.ClientSession

    async def on_end(session, ctx, params):
        h = params.response.headers
        peer = None
        conn = params.response.connection
        if conn is not None and conn.transport is not None:
            peer = conn.transport.get_extra_info("peername")
        hdr_log.write(json.dumps({
            "t": round(time.time(), 2), "method": method, "round": rnd,
            "url": str(params.url).rsplit("/", 1)[-1],
            "req_range": params.headers.get("Range"), "status": params.response.status,
            "content_range": h.get("Content-Range"), "content_length": h.get("Content-Length"),
            "etag": h.get("ETag"), "last_modified": h.get("Last-Modified"),
            "server": h.get("Server"), "via": h.get("Via"), "age": h.get("Age"),
            "peer": peer[0] if peer else None,
        }) + "\n")
        hdr_log.flush()

    def factory(*a, **kw):
        tc = aiohttp.TraceConfig()
        tc.on_request_end.append(on_end)
        kw["trace_configs"] = list(kw.get("trace_configs") or []) + [tc]
        return real(*a, **kw)

    return real, factory


def run_aseq(specs, dest_dir, protocol, hdr_log, method, rnd):
    opts = Options(engine="segmented", protocol=protocol, adaptive=False, jobs=len(specs),
                   quiet=True)
    eng = SegmentedEngine(opts, dest_dir)
    scheme = "https" if protocol == "https" else "ftp"
    tasks = [DownloadTask(f"{scheme}://{path}", name, name.split("_")[0])
             for name, _md5, _size, path in specs]
    RecordingGuard.instances.clear()
    real, factory = make_session_factory(hdr_log, method, rnd)
    aseq_batch.HostGuard = RecordingGuard
    aseq_batch.aiohttp.ClientSession = factory
    try:
        failed = asyncio.run(BatchDownloader(eng, opts, dest_dir).run(tasks))
    finally:
        aseq_batch.aiohttp.ClientSession = real
        aseq_batch.HostGuard = HostGuard
    g = RecordingGuard.instances[0] if RecordingGuard.instances else None
    extra = {"failed": sorted(failed),
             "guard_trips": len(g.trips) if g else None,
             "guard_trip_kinds": sorted({k for _h, k, _d in g.trips}) if g else None,
             "guard_min_cap": g.min_cap_seen if g else None,
             "guard_default_cap": g.default_cap if g else None}
    return extra


def run_curl(specs, dest_dir, scheme, out_dir, method, rnd):
    procs = []
    for name, _md5, _size, path in specs:
        dest = os.path.join(dest_dir, name)
        wfmt = (f"{name}\\t%{{http_code}}\\t%{{remote_ip}}\\t%{{size_download}}\\t"
                f"%{{time_total}}\\t%{{speed_download}}\\n")
        p = subprocess.Popen(["curl", "-sS", "--retry", "3", "-o", dest, "-w", wfmt,
                              f"{scheme}://{path}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        procs.append((name, p))
    rc = {}
    with open(os.path.join(out_dir, f"curl_{method}_{rnd}.tsv"), "w") as f:
        for name, p in procs:
            o, e = p.communicate()
            rc[name] = p.returncode
            f.write(o if o.endswith("\n") or not o else o + "\n")
            if e.strip():
                f.write(f"# {name} stderr: {e.strip()}\n")
    return {"failed": sorted(n for n, r in rc.items() if r != 0)}


def file_times(dest_dir, start):
    """Per-file finish time (mtime) relative to the pass start."""
    out = {}
    for n in os.listdir(dest_dir):
        p = os.path.join(dest_dir, n)
        if os.path.isfile(p) and n.endswith(".fastq.gz"):
            out[n] = round(os.path.getmtime(p) - start, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--methods", default="aseq-https,curl-ftp,aseq-ftp,curl-https")
    ap.add_argument("files", nargs="+", help="NAME=MD5=SIZE=FTP_PATH (path without scheme)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    good_dir = os.path.join(a.work, "good")
    bad_dir = os.path.join(a.work, "bad")
    os.makedirs(good_dir, exist_ok=True)
    os.makedirs(bad_dir, exist_ok=True)

    logging.basicConfig(filename=os.path.join(a.out, "engine.log"), level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    hdr_log = open(os.path.join(a.out, "https_headers.jsonl"), "a")
    files_tsv = open(os.path.join(a.out, "files.tsv"), "a")
    files_tsv.write("round\tmethod\tfile\tbytes\tfinish_s\tmd5\tmatch\n")
    passes_tsv = open(os.path.join(a.out, "passes.tsv"), "a")
    passes_tsv.write("round\tmethod\tstart\twall_s\tMBps\tfiles_ok\tfiles\tmismatches\textra\n")

    specs = [f.split("=", 3) for f in a.files]
    specs = [(n, m, int(s), p) for n, m, s, p in specs]
    want = {n: m for n, m, _s, _p in specs}
    sizes = {n: s for n, _m, s, _p in specs}
    total = sum(sizes.values())
    methods = a.methods.split(",")
    bad_entries = []

    for rnd in range(1, a.rounds + 1):
        order = methods if rnd % 2 else list(reversed(methods))
        for method in order:
            dest_dir = os.path.join(a.work, f"{method}_{rnd}")
            os.makedirs(dest_dir, exist_ok=True)
            t0 = time.time()
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            print(f"[{stamp}] round {rnd} {method}: start", flush=True)
            if method == "aseq-https":
                extra = run_aseq(specs, dest_dir, "https", hdr_log, method, rnd)
            elif method == "aseq-ftp":
                extra = run_aseq(specs, dest_dir, "ftp", hdr_log, method, rnd)
            elif method == "curl-ftp":
                extra = run_curl(specs, dest_dir, "ftp", a.out, method, rnd)
            elif method == "curl-https":
                extra = run_curl(specs, dest_dir, "https", a.out, method, rnd)
            else:
                raise SystemExit(f"unknown method {method}")
            wall = time.time() - t0
            times = file_times(dest_dir, t0)
            names = [n for n, *_ in specs]
            paths = [os.path.join(dest_dir, n) for n in names]
            with ProcessPoolExecutor(max_workers=8) as ex:
                got = list(ex.map(_md5_or_dash, paths))
            ok = mism = 0
            for n, p, h in zip(names, paths, got):
                match = h == want[n]
                files_tsv.write(f"{rnd}\t{method}\t{n}\t{os.path.getsize(p) if os.path.exists(p) else 0}"
                                f"\t{times.get(n, '')}\t{h}\t{match}\n")
                if match:
                    ok += 1
                    gp = os.path.join(good_dir, n)
                    if not os.path.exists(gp):
                        shutil.move(p, gp)
                elif h != "-":
                    mism += 1
                    if len(bad_entries) < MAX_BAD_KEPT:
                        bp = os.path.join(bad_dir, f"{method}_{rnd}_{n}")
                        shutil.move(p, bp)
                        bad_entries.append({"file": n, "method": method, "round": rnd, "path": bp})
            files_tsv.flush()
            passes_tsv.write(f"{rnd}\t{method}\t{stamp}\t{wall:.1f}\t{total / wall / 1e6:.2f}\t{ok}"
                             f"\t{len(names)}\t{mism}\t{json.dumps(extra)}\n")
            passes_tsv.flush()
            print(f"  {method} round {rnd}: {wall:.0f} s, {total / wall / 1e6:.1f} MB/s, "
                  f"{ok}/{len(names)} md5 OK, {mism} mismatched, {json.dumps(extra)}", flush=True)
            shutil.rmtree(dest_dir, ignore_errors=True)

    report = []
    for e in bad_entries:
        n = e["file"]
        gp = os.path.join(good_dir, n)
        if os.path.exists(gp):
            e.update(compare(e["path"], gp))
            segs = calculate_segments(sizes[n], min_file_size=5 * BLOCK, max_segments=8,
                                      segment_size=512 * BLOCK)
            e["segment_starts_MiB"] = [round(s / BLOCK, 2) for s, _ in segs]
        else:
            e["note"] = "no good copy of this file to compare against"
        report.append(e)
        print(json.dumps(e), flush=True)
    with open(os.path.join(a.out, "mismatches.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"done: {len(report)} mismatching copies examined", flush=True)


def _md5_or_dash(p):
    return md5_of(p) if os.path.exists(p) else "-"


if __name__ == "__main__":
    main()
