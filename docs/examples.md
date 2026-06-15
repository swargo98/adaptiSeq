# Examples

Copy-pasteable commands for common tasks. Screenshots are **TBD**.

## 1. Everything for a project (data + metadata)

```bash
adaptiseq -i PRJNA211801
```

Resolves every Run in the project, downloads each through the segmented engine,
and md5-verifies it.

## 2. Metadata only

```bash
adaptiseq -i PRJNA211801 -m
adaptiseq -i CRR343031 -m
```

→ `PRJNA211801.metadata.tsv` (and for GSA, `*.metadata.csv` + `CRA*.metadata.xlsx`).

## 3. Direct gzip FASTQ

```bash
adaptiseq -i SRR1178105 -g
```

## 4. Convert SRA → FASTQ (single-cell friendly)

```bash
adaptiseq -i SRR1178105 -q -t 10
```

## 5. Batch download a list, in parallel

```bash
adaptiseq -i accessions.txt -g            # adaptive worker pool (default)
adaptiseq -i accessions.txt -g -j 8 --no-adaptive   # fixed 8 workers
```

`accessions.txt` — one accession per line, databases may be mixed:

```
SRR7706354
PRJNA480016
CRR311377
GSM7417667
```

## 6. Merge an Experiment's Runs

```bash
adaptiseq -i SRX003906 -g -e ex
```

## 7. Aspera (ENA), adaptive pool

```bash
adaptiseq -i ena_list.txt -a --aspera-efficiency 0.8
```

## 8. Force a database / protocol

```bash
adaptiseq -i SRR1178105 -d sra
adaptiseq -i SRR7706354 -g -r https
```

## 9. From Python

```python
from adaptiseq import fetch, get_metadata

rows   = get_metadata("SRR7706354")
result = fetch("accessions.txt", outdir="data/", gzip=True, jobs=20, adaptive=True)
print(result.success_ids, result.fail_ids, result.failed)
```

## 10. Resume an interrupted run

Just re-run the same command. Completed Runs in `success.log` are skipped, and
partially downloaded files (`*.part`/`*.part.meta`) are resumed, not restarted. To
force a re-download of one Run:

```bash
sed -i '/SRR7706354/d' success.log
adaptiseq -i SRR7706354 -g
```
