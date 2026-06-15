# Method details

adaptiSeq fetches every sequence-data byte through a single **download seam**, so
the scheduler and engines change only *how* bytes arrive and *when* files are
scheduled — never *which* bytes. Resolution, metadata, integrity, logs, and merge
stay byte-for-byte faithful to `iseq`.

## Engines

| Engine | Flag | What it is |
| ------ | ---- | ---------- |
| **segmented** *(default)* | `--engine segmented` | Resumable, range-based HTTP(S)/FTP downloader (`aiohttp`/`aioftp`). Each file is fetched in multiple byte-range connections with atomic `.part`/`.part.meta` resume. Runs the batch worker pool and adaptive controller. |
| **classic** *(opt-in)* | `--engine classic` | The faithful `iseq` path: `wget`, or `axel` with `-p`, plus `ascp` for `-a`. No segmentation. |

> The segmented engine **never falls back to classic**. A host that cannot serve
> ranges is downloaded as a **single stream inside the segmented engine**;
> `--engine classic` is a manual choice only.

## Transport selection (segmented, protocol `auto`)

For ENA the default is **HTTPS-first**:

1. Prefer the **HTTPS** mirror, confirmed by a cheap per-host range probe.
2. Else native **segmented FTP** (`REST`/`RETR` via `aioftp`).
3. Else a **single stream** inside the segmented engine.

`-r https` / `-r ftp` overrides and is final. A corrupt or zero-byte file is never
produced. Per-host transport is cached by **kind, not URL** (a deliberate fix — a
URL cache made every file on a host download the first file's bytes).

## Download methods summary

| Method | Used for | Notes |
| ------ | -------- | ----- |
| `segmented-https` | ENA/most HTTPS mirrors | default; multi-range, resumable |
| `segmented-ftp` | ENA FTP (`REST`/`RETR`) | when HTTPS ranges unavailable |
| `single-stream` | range-incapable hosts | inside the segmented engine; never truncated |
| `aspera (ena)` | ENA, `-a` | adaptive `ascp` pool (efficiency hysteresis) |
| `aspera (gsa)` | GSA, `-a` | sequential, Huawei-Cloud preferred; best-effort |
| `huawei-cloud` | GSA | preferred for GSA even with `-a` (inherited from iseq) |
| `classic wget/axel` | `--engine classic` | the faithful iseq path; `axel` with `-p` |

## Concurrency & etiquette

- **Per-file:** up to `--max-segments` byte-range connections.
- **Per-host:** a global cap (`--max-conns-per-host`) plus a reactive circuit
  breaker (429/503/refused → exponential global backoff + temporarily lowered
  cap, slow recovery).
- **Per-batch:** a worker pool (`-j`) whose active size the gradient controller
  tunes (`--adaptive`); workers are gated at file-pickup boundaries.
- **Resolution:** parallel (`--meta-jobs`) under per-endpoint rate limiters
  (ENA / NCBI / GSA; NCBI 3 rps, 10 with `NCBI_API_KEY`).
- **Speed:** `-s/--speed` token-bucket cap in MB/s.

## Integrity

Every Run is md5-checked against the public database (SRA uses md5 +
`vdb-validate`). On mismatch adaptiSeq retries up to **three rounds**, then records
the outcome in `success.log` / `fail.log`. `-k/--skip-md5` disables the checks.
