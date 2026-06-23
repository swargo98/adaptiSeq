# adaptiSeq — TestPyPI release + Google Colab acceptance test

This is the dress rehearsal before shipping to the real PyPI: publish `adaptiseq`
to **TestPyPI**, then install it on a clean **Google Colab** box and exercise
**every feature in the README and `docs/`** against the live databases.

There are two parts:

- **Part A — Publish to TestPyPI** (run on your dev machine).
- **Part B — Test on Colab** (install from TestPyPI + run the acceptance script).

The acceptance script is [`bench/colab_acceptance.sh`](bench/colab_acceptance.sh).
It uses small accessions so it finishes quickly; the heavy paths (merge ~1 GB,
Aspera ~tens of MB) are gated behind `TIER=full`.

---

## Accessions used (and why)

The medium list `bench/inputs/accessions_medium_PRJNA353374.txt` (project
**PRJNA353374**, runs `SRR5017128…SRR5017139`) **does have ENA Aspera links**
(`fasp.sra.ebi.ac.uk:/…`), so no substitute list was needed for Aspera. But each
file is **~3.5–5 GB** (≈54 GB for all 12) — too heavy to download repeatedly on
Colab. So the script downloads small accessions for the functional checks and uses
the full medium list only for the **cheap, no-download paths** (parallel metadata
resolution and project-level resolution).

| Feature under test | Accession(s) | Size | Source |
| --- | --- | --- | --- |
| Metadata only (`-m`) | SRR1553469, ERR1726497, DRR291041, GSM7417667, CRR311377 | tiny | SRA / ENA / DDBJ / GEO / GSA |
| Project resolution | **PRJNA353374** (the medium list's project) | metadata only | SRA |
| Parallel metadata batch | **accessions_medium_PRJNA353374.txt** (all 12) | metadata only | SRA/ENA |
| Raw `.sra` (default) | SRR1553469 | 4.5 MB | NCBI SRA |
| Gzip FASTQ (`-g`) | SRR1553469 (paired) | 4.5 MB | ENA |
| SRA→FASTQ (`-q`, `-q -g`) | SRR1553469 | 4.5 MB | ENA/SRA |
| Transport (`-r https`/`-r ftp`, `-d sra`) | SRR1553469, ERR1726497 | tiny | ENA/SRA |
| Batch (mixed DBs) | `bench/inputs/colab_batch_mixed.txt` | ~30 MB | SRA+ENA+DDBJ |
| Merge (`-e ex`, **full tier**) | SRX003906 (5 runs) | ~1 GB | ENA |
| Aspera (`-a`, **full tier**) | `bench/inputs/colab_aspera_ena.txt` | ~17 MB | ENA |
| Python API | SRR1553469 + mixed list | tiny | — |

> Want a genuine **~1 GB Aspera** download (as originally floated)? Put
> `ERR2208674` (1.26 GB, single-end, has Aspera) in `colab_aspera_ena.txt`.

---

## Part A — Publish to TestPyPI

> TestPyPI is a **separate** index from PyPI with its own account and tokens. It's
> a throwaway sandbox — packages there don't affect the real PyPI.

### A1. One-time setup

1. Create an account at **https://test.pypi.org/account/register/** and verify the
   email.
2. Create an API token at **https://test.pypi.org/manage/account/token/** (scope:
   "Entire account" is fine for testing). Copy it — it starts with `pypi-…`.
3. Put it in `~/.pypirc` so `twine` finds it automatically:

   ```ini
   [distutils]
   index-servers =
       testpypi

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-AgENdGVzdC5weXBpLm9yZ...   # your TestPyPI token
   ```

   (`__token__` is the literal username for token auth.)

### A2. Build the distributions

From the repo root (use `python3` if your machine has no `python` shim):

```bash
python -m pip install --upgrade build twine
rm -rf dist/ build/ *.egg-info        # clean old artifacts
python -m build                        # -> dist/adaptiseq-0.1.0.tar.gz + .whl
python -m twine check dist/*           # validates metadata + README rendering
```

`twine check` must say **PASSED** for both files before you upload.

### A3. Upload to TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

It prints a URL like `https://test.pypi.org/project/adaptiseq/0.1.0/`. Open it and
confirm the README renders and the metadata looks right.

> **Name already taken on TestPyPI?** Upload fails with a 403. TestPyPI is shared,
> so `adaptiseq` may already exist from someone else. For a test-only run, bump the
> name temporarily (e.g. set `name = "adaptiseq-swargo98"` in `pyproject.toml`),
> rebuild, re-upload — then revert before the real PyPI release. The real PyPI name
> is reserved separately.
>
> **Re-uploading the same version fails** (409) — PyPI/TestPyPI never let you
> overwrite a version. Bump `__version__` in `adaptiseq/__init__.py` (e.g.
> `0.1.0.post1`) and rebuild.

---

## Part B — Test on Google Colab

Open a new notebook at **https://colab.research.google.com** and run these as
cells (top to bottom). `!` runs a shell command; `%%bash` runs a whole cell.

### B1. Install adaptiSeq from TestPyPI

TestPyPI does **not** mirror normal dependencies (aiohttp, aioftp, numpy,
openpyxl), so you **must** add real PyPI as an extra index — otherwise pip can't
resolve the deps:

```python
!pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "adaptiseq[xlsx]"
!adaptiseq --version
```

> If you used a temporary name in A3, install that name instead (e.g.
> `adaptiseq-swargo98`); the import and `adaptiseq` command stay the same.

### B2. Install the external CLI tools

adaptiSeq shells out to the same tools `iseq` does. Two options:

**Option 1 — apt + pip (fast; covers everything except Aspera).**

```bash
%%bash
apt-get -qq update
apt-get -qq install -y sra-toolkit pigz wget coreutils
which wget md5sum srapath fasterq-dump vdb-validate pigz
```

**Option 2 — conda/bioconda (slower, but also gets real IBM `ascp` for Aspera).**

```python
!pip install -q condacolab
import condacolab; condacolab.install()      # restarts the kernel — expected
```

```bash
%%bash
# after the kernel restarts, in a new cell:
mamba install -y -c conda-forge -c bioconda sra-tools pigz wget aspera-cli
which ascp fasterq-dump   # ascp's key lives at ../etc/aspera/ relative to it
```

> **Aspera on Colab is a known gamble.** FASP runs over **UDP 33001**, and Colab
> frequently blocks outbound UDP. If the Aspera test times out, that's the network,
> not adaptiSeq — the HTTPS/FTP paths (tested in the same run) are the proof the
> tool works. The script flags this case explicitly.

### B3. Get the test inputs + script

```bash
%%bash
git clone --depth 1 https://github.com/swargo98/adaptiSeq.git
cd adaptiSeq && ls bench/inputs/ bench/colab_acceptance.sh
```

### B4. Run the acceptance test

**Quick tier** (small downloads only, ~a few minutes, no Aspera/merge):

```bash
%%bash
cd adaptiSeq
TIER=quick bash bench/colab_acceptance.sh
```

**Full tier** (adds the ~1 GB merge + Aspera; needs Option 2 above for `ascp`):

```bash
%%bash
cd adaptiSeq
TIER=full bash bench/colab_acceptance.sh
```

Run Aspera without the heavy merge:

```bash
%%bash
cd adaptiSeq
ASPERA=1 bash bench/colab_acceptance.sh
```

### B5. Read the result

The script prints a per-check `PASS/FAIL/SKIP` table and a final summary, e.g.:

```
SUMMARY   PASS=24  FAIL=0  SKIP=3
...
ALL GREEN
```

- **PASS** — the command ran and produced the expected artifact (file, log line).
- **SKIP** — a tool was missing (e.g. no `ascp`) or the tier excludes it; not a
  failure.
- **FAIL** — investigate; per-test logs are under the printed `Artifacts under:`
  directory (each test writes its own `log.txt`).

Exit code is `0` only if there are **no FAILs**.

---

## What the script covers (maps to the docs)

| § in script | README / docs feature |
| --- | --- |
| 1 | `--version`, `--help` |
| 2 | `-m` metadata for **GSA/SRA/ENA/DDBJ/GEO** + **project** resolution |
| 3 | Raw `.sra` download (default engine) — *non-batch* |
| 4 | `-g` direct gzip FASTQ |
| 5 | `-q` SRA→FASTQ and `-q -g` convert-then-gzip |
| 6 | `-r https`, `-r ftp`, `-d sra` (transport / source selection) |
| 7 | `-j` / `--adaptive` / `--no-adaptive` / `--meta-jobs` (**batch**) |
| 8 | Resume / skip already-completed runs |
| 9 | `-s` speed cap, `-k` skip-md5, `-Q` quiet |
| 10 | `-e ex` merge per Experiment (*full tier*) |
| 11 | `-a` Aspera, ENA adaptive pool (*full tier / `ASPERA=1`*) |
| 12 | Python API: `get_metadata`, `resolve`, `fetch`, typed exceptions |
| 13 | Error handling / preflight (expected non-zero exits) |

---

## Manual one-liners (if you'd rather click through the docs by hand)

```bash
adaptiseq --version
adaptiseq -i SRR1553469 -m                         # SRA metadata
adaptiseq -i CRR311377  -m                         # GSA metadata (.csv + .xlsx)
adaptiseq -i GSM7417667 -m                         # GEO -> SRA
adaptiseq -i PRJNA353374 -m                         # project (all 12 runs)
adaptiseq -i SRR1553469                            # raw .sra
adaptiseq -i SRR1553469 -g                         # gzip FASTQ
adaptiseq -i SRR1553469 -q -t 4                    # SRA -> FASTQ
adaptiseq -i SRR1553469 -g -r https                # force HTTPS
adaptiseq -i bench/inputs/colab_batch_mixed.txt -g # batch (adaptive)
adaptiseq -i bench/inputs/colab_batch_mixed.txt -g -j 2 --no-adaptive
adaptiseq -i bench/inputs/colab_aspera_ena.txt -a -g --aspera-efficiency 0.8
adaptiseq -i SRX003906 -g -e ex                    # merge experiment (~1 GB)
```

```python
from adaptiseq import fetch, resolve, get_metadata
rows = get_metadata("SRR1553469")
urls = resolve("SRR1553469", database="ena", gzip=True)
res  = fetch("bench/inputs/colab_batch_mixed.txt", outdir="data/", gzip=True)
print(res.success_ids, res.fail_ids, res.failed)
```
