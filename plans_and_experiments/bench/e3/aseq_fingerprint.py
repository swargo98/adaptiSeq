#!/usr/bin/env python3
"""Identify exactly which adaptiSeq build an E3 arm is about to run.

The paper cites one archived release, so every TSV row must be traceable to it.
`adaptiseq --version` alone is not enough: an editable install, or a wheel
rebuilt from a dirty tree, reports the same version string as the release.

Prints one line of `key=value` pairs for the harness to splice into its TSV row:

    aseq_version=0.1.5 aseq_sha256=<64 hex>          # --wheel given and it matches
    aseq_version=0.1.5 aseq_sha256=tree:<64 hex>     # no --wheel

With `--wheel PATH` the sha256 is that of the wheel FILE (the number PyPI shows
under "view hashes"), and it is reported only if every file inside the wheel is
byte-identical to the file Python actually imports. Otherwise this exits 1: the
installed package is not that wheel.

Without `--wheel` the digest covers the imported package tree (sorted relative
path + content of every non-bytecode file). It is still comparable across
machines and across rows, it just cannot be looked up on PyPI -- hence the
`tree:` prefix, so the two kinds are never confused.

    python bench/e3/aseq_fingerprint.py [--wheel adaptiseq-0.1.5-py3-none-any.whl]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path


def sha256_file(path: Path, _bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(_bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def tree_digest(pkg_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(pkg_dir.rglob("*")):
        if not p.is_file() or p.suffix in (".pyc", ".pyo") or "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(pkg_dir).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def wheel_mismatches(wheel: Path, pkg_dir: Path) -> list[str]:
    """Package files in the wheel that differ from (or are missing in) pkg_dir."""
    bad = []
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            if not name.startswith("adaptiseq/") or name.endswith("/"):
                continue
            installed = pkg_dir.parent / name
            if not installed.is_file() or installed.read_bytes() != zf.read(name):
                bad.append(name)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheel", type=Path, help="the release wheel the install must match")
    args = ap.parse_args()

    try:
        import adaptiseq
    except ImportError as exc:
        print(f"adaptiseq is not importable: {exc}", file=sys.stderr)
        return 1
    pkg_dir = Path(adaptiseq.__file__).resolve().parent

    if args.wheel:
        if not args.wheel.is_file():
            print(f"wheel not found: {args.wheel}", file=sys.stderr)
            return 1
        bad = wheel_mismatches(args.wheel, pkg_dir)
        if bad:
            print(
                f"installed adaptiseq ({pkg_dir}) does not match {args.wheel.name}: "
                f"{len(bad)} file(s) differ, e.g. {bad[0]}",
                file=sys.stderr,
            )
            return 1
        digest = sha256_file(args.wheel)
    else:
        digest = "tree:" + tree_digest(pkg_dir)

    print(f"aseq_version={adaptiseq.__version__} aseq_sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
