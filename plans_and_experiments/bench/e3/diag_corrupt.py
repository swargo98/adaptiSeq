"""Download the same ENA files again and again, and look at any md5 mismatch.

Gate job 54902879, panel 3b, arm adaptiseq-default: SRR15852411 failed its md5
check three times in a row (batch download of _1, a fresh _1, then a fresh _2),
all over HTTPS, while the other seven runs and the earlier arms verified. TLS
rules out corruption in transit, and the log shows no failed segment (only
refused connects, which write nothing), so the bytes were either served wrong
or written wrong. This tells the two apart:

* each file is fetched with adaptiSeq's own SegmentedDownloader (ranged HTTPS
  GETs, the code under test) and with one plain curl HTTPS stream;
* every response's status, Content-Range, ETag, Last-Modified and Server
  headers are logged, so a range served from a different copy shows up;
* a mismatching copy is kept and compared, 1 MiB block by block, with a copy
  that matched: where the bad blocks sit (relative to the segment boundaries)
  and whether they are zeros says which side wrote them.

Usage (from the repo root, inside the benchmark env):
    python plans_and_experiments/bench/e3/diag_corrupt.py --out DIR --work DIR \
        --iters 5 ACC_FILE=MD5=SIZE=HTTPS_URL ...
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time

import aiohttp

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from adaptiseq.engine.segmented import SegmentedDownloader  # noqa: E402

BLOCK = 1024 * 1024


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 * BLOCK), b""):
            h.update(b)
    return h.hexdigest()


async def seg_download(url, dest, hdr_log):
    async def on_end(session, ctx, params):
        h = params.response.headers
        hdr_log.write(json.dumps({
            "t": round(time.time(), 2), "file": os.path.basename(dest),
            "req_range": params.headers.get("Range"), "status": params.response.status,
            "content_range": h.get("Content-Range"), "etag": h.get("ETag"),
            "last_modified": h.get("Last-Modified"), "server": h.get("Server"),
            "via": h.get("Via"), "age": h.get("Age"),
        }) + "\n")
        hdr_log.flush()

    tc = aiohttp.TraceConfig()
    tc.on_request_end.append(on_end)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=0),
                                     trace_configs=[tc]) as s:
        d = SegmentedDownloader(s, url, dest)
        ok = await d.download()
        return ok, d.calculate_segments(os.path.getsize(dest)) if ok else []


def curl_download(url, dest, hdr_path):
    rc = subprocess.call(["curl", "-sS", "-D", hdr_path, "-o", dest, url])
    return rc == 0


def compare(bad, good):
    """Return a summary of the 1 MiB blocks that differ."""
    diff, zero = [], 0
    with open(bad, "rb") as fb, open(good, "rb") as fg:
        i = 0
        while True:
            b, g = fb.read(BLOCK), fg.read(BLOCK)
            if not b and not g:
                break
            if b != g:
                diff.append(i)
                if b.strip(b"\0") == b"":
                    zero += 1
                if len(diff) == 1:
                    # first differing byte inside the first bad block
                    first = next(k for k in range(min(len(b), len(g))) if b[k] != g[k]) \
                        if len(b) and len(g) else 0
                    first_byte = i * BLOCK + first
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("files", nargs="+", help="NAME=MD5=SIZE=HTTPS_URL")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    hdr_log = open(os.path.join(a.out, "seg_headers.jsonl"), "a")
    res = open(os.path.join(a.out, "downloads.tsv"), "a")
    res.write("iter\tmethod\tfile\tok\tsize\tseconds\tmd5\tmatch\n")
    specs = [f.split("=", 3) for f in a.files]
    good, bad = {}, []
    for it in range(1, a.iters + 1):
        for name, want, size, url in specs:
            for method in ("seg", "curl"):
                dest = os.path.join(a.work, f"{method}_{it}_{name}")
                t0 = time.time()
                if method == "seg":
                    ok, segs = asyncio.run(seg_download(url, dest, hdr_log))
                else:
                    ok = curl_download(url, dest, os.path.join(a.out, f"curl_{it}_{name}.headers"))
                    segs = []
                dt = time.time() - t0
                got = md5_of(dest) if os.path.exists(dest) else "-"
                match = got == want
                res.write(f"{it}\t{method}\t{name}\t{ok}\t{os.path.getsize(dest) if os.path.exists(dest) else 0}"
                          f"\t{dt:.1f}\t{got}\t{match}\n")
                res.flush()
                print(f"iter {it} {method:4s} {name}: ok={ok} {dt:.0f}s md5 {'OK' if match else 'MISMATCH'}"
                      + (f" segments={segs}" if segs else ""), flush=True)
                if match and name not in good:
                    good[name] = dest
                elif not match and os.path.exists(dest):
                    bad.append((name, method, it, dest, segs))
                    continue
                if good.get(name) != dest and os.path.exists(dest):
                    os.remove(dest)
                for leftover in (dest + ".part", dest + ".part.meta"):
                    if os.path.exists(leftover):
                        os.remove(leftover)
    report = []
    for name, method, it, dest, segs in bad:
        entry = {"file": name, "method": method, "iter": it}
        if name in good:
            entry.update(compare(dest, good[name]))
            entry["segment_starts"] = [s for s, _ in segs]
        else:
            entry["note"] = "no matching copy to compare against"
        report.append(entry)
        print(json.dumps(entry), flush=True)
    with open(os.path.join(a.out, "mismatches.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"done: {len(bad)} mismatching download(s)")


if __name__ == "__main__":
    main()
