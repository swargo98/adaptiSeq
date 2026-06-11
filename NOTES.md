# adaptiSeq Part 1 — Implementation plan, parity checklist, and divergence log

This file is the written plan required by Section 9.1 of the build spec, the
parity checklist derived from Sections 3 and 4, and the running log of every
deliberate judgement call where the Python port diverges from the Bash original.

Divergence policy: divergences must be **deliberate and documented**, never
accidental. Every entry below names the Bash behaviour, the Python behaviour, and
the reason.

---

## 1. Plan (build order, per Section 9.2)

1. Scaffold the installable package + console entry point + the engine seam.
2. Accession validation (`validateQuery`) + routing (GSA vs SRA/ENA).
3. Metadata fetching for ENA, SRA-fallback, and GSA (CSV + XLSX).
4. Per-run URL resolution (`downloadSRA` / `downloadGSA`) through the classic seam.
5. Integrity (`checkSRA` / `checkGSA`) + `success.log` / `fail.log`.
6. Conversion (`fasterq-dump` + `pigz`) and merge (`mergeSRArun` / `mergeGSArun`).
7. The per-accession process loop and the file-list input path.
8. Public library API (`fetch`, `resolve`, `get_metadata`).
9. Differential harness + golden fixtures + unit tests + API-drift canary.
10. README, CHANGES_FROM_ISEQ, iSeq.yml, install verification.

## 2. Architecture decisions

- **Metadata bytes come from `wget`, not `requests`.** iseq fetches every metadata
  file by shelling to `wget` with specific flags, user-agents, and POST bodies.
  To guarantee byte-for-byte parity (acceptance criterion 3), adaptiSeq shells to
  the same `wget` invocations rather than reimplementing the HTTP with `requests`.
  This also honours the spec's "otherwise keep shelling to `wget` as `iseq` does"
  and keeps `requests` out of the hard dependency set. All network I/O for
  metadata/GEO/GSA-search/spider-size lives in `adaptiseq/net.py`.
- **The engine seam** (`adaptiseq/engine/classic.py::ClassicEngine.fetch`) is the
  single place bytes of *sequence data* are pulled. `downloadSRA`/`downloadGSA`
  ports in `resolve.py` call `engine.fetch(url, dest)` (wget/axel) or
  `engine.fetch_aspera(link, db)` (ascp). Part 2 swaps the engine without touching
  resolution, integrity, logging, or merge.
- **Global Bash state becomes an `Options`/`RunContext` dataclass** threaded
  explicitly instead of shell globals (`gzip`, `fastq`, `database`, `parallel`,
  `aspera`, `speed`, `skip_md5`, `protocol`, `quiet`, `metadata`, `merge`,
  `threads`, `output`). `database` is mutable per the Bash (ENA→SRA fallback).
- **Colour output is produced only by the CLI's reporter**, never by the library
  functions, satisfying Section 6 ("must not call sys.exit or print colour
  codes"). `adaptiseq/console.py` holds `AnsiReporter` (exact bash escape codes)
  and `NullReporter`. Library API uses `NullReporter` by default.

## 3. Parity checklist — fidelity requirements (Section 3)

- [ ] URL resolution identical: `downloadSRA`/`downloadGSA`/`getSRAMetadata`/
      `getGSAMetadata`/`validateQuery` ported faithfully (ENA vol path, srapath,
      GSA Huawei vs ftp, fastq.gz vs .sra, `-d`/`-g`/`-a`/`-r` interactions).
- [ ] Metadata endpoints + filenames + formats + columns + user-agents identical.
- [ ] Accession regexes copied verbatim (see `accession.py` docstrings).
- [ ] MD5/integrity policy identical: `vdb-validate` for `.sra`, md5-vs-metadata
      for `.fastq.gz`, GSA vs project `md5sum.txt`; ≤3 rounds then `fail.log`;
      `success.log` line format `$(date)\t$ID`; `-k` skips.
- [ ] Resume/skip identical: ID already in `success.log` is skipped with same msg.
- [ ] External tools shelled out, not reimplemented (fasterq-dump, pigz,
      vdb-validate, srapath, ascp, md5sum, wget, axel). `CheckSoftware` → preflight.
- [ ] Merge (`-e ex|sa|st`) reproduces symlink/rename/concatenate logic incl.
      single-run rename and differing-prefix cases.
- [ ] Coloured `Note`/`Error`/`How to solve?` message style matched exactly.

## 4. Parity checklist — CLI flags (Section 4)

`-i/--input`, `-m/--metadata`, `-g/--gzip`, `-q/--fastq`, `-t/--threads` (8),
`-e/--merge [ex|sa|st]`, `-d/--database [ena|sra]` (auto), `-a/--aspera`,
`-s/--speed` (1000), `-k/--skip-md5`, `-r/--protocol [ftp|https]` (ftp),
`-Q/--quiet`, `-o/--output`, `-p/--parallel`, `-h/--help`, `-v/--version`
(`adaptiSeq 0.1.0`), `--engine [segmented|classic]` (classic-only in Part 1).

## 5. Deliberate divergences from the Bash (with reasons)

1. **Preflight runs after argparse handles `--help`/`--version`.** In Bash,
   `CheckSoftware` runs at the very top, so even `iseq --help` requires all 7
   tools present. Acceptance criteria 1 & 2 require `adaptiseq --help`/`--version`
   to work unconditionally, and argparse exits on those during parsing. So
   adaptiSeq runs the tool preflight only for real work (after help/version).
   Same tools, same messages, same exit code — just gated to not block help.
2. **Per-run retry counter resets per Run.** In Bash, `count` is a single global
   that is *not* reset between Runs inside one accession's subshell, so a Run that
   exhausts its 3 retries leaves `count=4`, sending every subsequent Run in that
   accession straight to `fail.log` without retrying. The README documents "a
   maximum of three rounds" *per Run*. adaptiSeq resets the retry counter per Run
   (the documented intent). This only differs from Bash after a hard failure, and
   the differential harness compares `success.log`/`fail.log` as sets of IDs, so
   the common (all-success) path is unaffected.
3. **`file`-based text detection for input.** Bash uses `file "$input" | grep -q
   'text'` to decide single-accession vs file-list, and `sed -i 's/\r$//'` to strip
   CRLF. adaptiSeq treats `-i` as a file when a path exists at that string and is a
   regular file; otherwise a single accession. CRLF is stripped on read. This is
   behaviourally equivalent for the documented "one accession per line" files and
   avoids depending on libmagic, while a real accession string (e.g. `SRR7706354`)
   is never an existing path.

4. **Needs-based tool preflight.** iseq runs ``CheckSoftware`` for all seven
   tools (``wget axel pigz ascp md5sum srapath vdb-validate``) unconditionally at
   startup, so even ``iseq -i X -m`` (metadata only) refuses to run without, say,
   ``axel`` or ``sra-tools`` installed. adaptiSeq's CLI runs a *needs-based*
   preflight: metadata-only (``-m``) requires only ``wget``; a real download
   requires the full base set (plus ``fasterq-dump`` for ``-q``/``-e``, ``axel``
   for ``-p``), exactly as iseq's download path does. This is strictly more
   permissive: it only ever *admits* a run iseq would reject for a missing tool
   the run never uses; it never rejects a run iseq would accept. It also makes the
   metadata-parity differential test runnable on machines without sra-tools.

5. **GSA retry restructured to a per-file loop.** iseq's ``checkGSA`` triggers a
   re-download by recursively calling ``downloadGSA`` (which re-fetches *every*
   file of the CRR) and shares the process-global ``count``. adaptiSeq runs the
   md5 retry as a per-file loop that re-fetches only the failing file, with the
   counter reset per file (same family as divergence #2). Observable
   ``success.log``/``fail.log`` ID sets are identical for the common path; only
   the wasteful re-fetch-everything behaviour on a hard md5 failure differs.

6. **The `$$SaveName` Bash quirk is corrected.** Several iseq "already
   downloaded" messages contain ``sed -i '/$$SaveName/d'`` where ``$$`` expands to
   the shell PID, producing nonsense like ``/12345SaveName/``. adaptiSeq renders
   the intended ``sed -i '/SaveName/d' success.log``. Cosmetic stdout only; the
   harness compares log contents, not these hints.

7. **`adaptiseq.resolve` (the public function) shadows the `resolve.py`
   submodule.** Section 6 mandates ``from adaptiseq import resolve`` to be the
   URL-resolving *function*, while Section 5 names ``resolve.py`` as a module.
   The public function wins at the package namespace; the submodule is internal
   and reached by internal aliased imports (``from . import resolve as _resolve``)
   or, in tests, via ``importlib.import_module("adaptiseq.resolve")``. Not a
   behavioural divergence from iseq (which has no library API) — just a naming
   note for maintainers.

(Append further entries here as they arise during implementation.)
