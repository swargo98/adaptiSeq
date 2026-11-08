# Usage overview

```bash
adaptiseq -i accession [options]
```

`-i/--input` takes a **single accession** or a **file** with one accession per
line. adaptiSeq first retrieves the accession's metadata, then downloads each Run
it contains, verifies md5, and (optionally) converts/merges.

## Full option list

```
Usage:
  adaptiseq -i accession [options]

Required:
  -i, --input     [text|file]   Single accession or a file containing multiple accessions.
                                Note: only one accession per line in the file.

Optional:
  -m, --metadata                Skip the sequencing data downloads and only fetch metadata.
  -g, --gzip                    Download FASTQ files in gzip format directly (*.fastq.gz).
  -q, --fastq                   Convert SRA files to FASTQ format.
  -t, --threads   int           Threads for SRA->FASTQ / compression (default: 8).
  -e, --merge     [ex|sa|st]    Merge fastq files per Experiment, Sample, or Study.
  -d, --database  [ena|sra]     Force database for SRA data (default: auto-detect).
      --no-sra-fallback         Fail a Run that ENA cannot serve instead of fetching it from SRA,
                                so every kept file can be checked against ENA's md5.
  -p, --parallel  int           axel connection count (classic engine only), e.g. -p 10.
  -a, --aspera                  Use Aspera (ascp); GSA/ENA only.
  -s, --speed     int           Download speed limit (MB/s) (default: 1000).
  -k, --skip-md5                Skip the md5 check for downloaded files.
  -r, --protocol  [ftp|https]   ENA transport (default: auto, HTTPS-first).
  -Q, --quiet                   Suppress download progress bars.
  -o, --output    text          Output directory (created if missing; default: cwd).

Engine / batch / adaptive:
  --engine        [segmented|classic]   Download engine (default: segmented).
  --segment-size  int           Target segment size in MB (default: 512).
  --max-segments  int           Max connections per file (default: 8).
  --max-conns-per-host int      Cap on connections to one host (default: auto = -j x --max-segments;
                                the circuit breaker still lowers it on 429/503).
  -j, --jobs      int           Max worker-pool size for batch download (default: 20).
  --adaptive / --no-adaptive    Adaptive concurrency (default: on); --no-adaptive runs all -j workers.
  --controller    name          Adaptive controller: topdown (default), bottomup, budget, greedy, knee.
  --probe-window  int           Adaptive probe window in seconds (default: 5).
  --cc-penalty    float         Worker-cost penalty K in score=throughput/K**workers (default: 1.01).
  --meta-jobs     int           Parallelism for metadata/URL resolution (default: 3).
  --aspera-efficiency float     Keep an extra ascp worker only above this efficiency (default: 0.70).

  -h, --help                    Show help.
  -v, --version                 Show version.
```

## Where to go next

- [Downloading sequence data](download.md) — the default download path, `-g`, `-q`, `-d`, `-r`, `-p`
- [Fetching metadata](metadata.md) — `-m`, and what files you get per database
- [Merging FASTQ](merge.md) — `-e ex|sa|st`
- [Batch & adaptive download](batch.md) — accession lists, `-j`, `--adaptive`, `--meta-jobs`
- [Aspera](aspera.md) — `-a` and the adaptive `ascp` pool
- [Python API](python-api.md) — `fetch`, `resolve`, `get_metadata`

## Logs and re-runs

| File | Contents |
| ---- | -------- |
| `success.log` | Runs downloaded and verified |
| `fail.log` | Runs that failed after 3 retry rounds |

**Exit status:** `0` when every requested Run was delivered, `1` when any Run failed
(named in `fail.log`) or the command could not run. A Run fetched from NCBI SRA because
ENA could not serve it is announced and counts as delivered, unless `--no-sra-fallback`
is given, in which case it fails.

A Run already in `success.log` is **skipped** on re-run; remove its line (e.g.
`sed -i '/SRR7706354/d' success.log`) to force a re-download. Partial files left
by the segmented engine (`*.part`, `*.part.meta`) are **resumed**, not restarted.
