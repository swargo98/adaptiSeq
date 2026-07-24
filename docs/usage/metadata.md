# Fetching metadata (`-m`)

Download only the sample metadata for an accession and skip the sequence data.

```bash
adaptiseq -i PRJNA211801 -m
adaptiseq -i CRR343031 -m
```

Metadata is always fetched (with or without `-m`) because it drives resolution; if
metadata cannot be retrieved, adaptiSeq stops before downloading. The metadata
bytes are pulled with `wget`, so the files are exactly what the archive serves.

## SRA / ENA / DDBJ / GEO

adaptiSeq first queries **ENA**. If sample information is available it downloads
metadata in **TSV** format via the
[ENA Portal API](https://www.ebi.ac.uk/ena/portal/api/swagger-ui/index.html)
(typically ~191 columns), saved as **`${accession}.metadata.tsv`**.

If ENA has no record yet (common for very recently released SRA data), adaptiSeq
falls back to the [SRA Database Backend](https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/),
downloading **CSV** (~30 columns) and converting it to TSV for consistency.

## GSA

For **GSA** accessions, adaptiSeq uses GSA's `getRunInfo` interface to download
**CSV** metadata (~25 columns), saved as **`${accession}.metadata.csv`**, and the
`exportExcelFile` interface for the parent Project's **XLSX** (sheets `Sample`,
`Experiment`, `Run`), saved as **`CRA*.metadata.xlsx`**.

## In the Python API

`get_metadata` returns the parsed rows as a list of dicts (and writes the same
files):

```python
from adaptiseq import get_metadata

rows = get_metadata("SRR7706354")          # ENA/SRA -> list[dict] of TSV columns
rows = get_metadata("CRR311377")           # GSA     -> list[dict] of CSV columns
```

See the [Python API](python-api.md) page.

## Output

| Database | Files |
| -------- | ----- |
| SRA / ENA / DDBJ / GEO | `${accession}.metadata.tsv` |
| GSA | `${accession}.metadata.csv`, `CRA*.metadata.xlsx` |

> **Note**
> NCBI E-utilities is rate-limited to **3 req/s** without a key and **10 req/s**
> with one. Set `NCBI_API_KEY` (and optionally `NCBI_EMAIL`) in the environment
> to use the higher limit when resolving large batches.
