# adaptiSeq system benchmark — results

Per-second resource sampling of each tool's process tree, attributed to the four task phases (request / metadata / data / md5). `*_mbps` columns are **megabytes/s** (decimal MB). Net is system-wide.

## Headline (per run, mean ± sd)

| tool | runs | wall s | bytes MB | formats |
|---|---|---|---|---|
| adaptiseq-classic | 2 | 3.3±0.2 | 179.0 | .fastq.gz |
| sra-toolkit | 2 | 25.1±0.2 | 311.3 | .sra |
| adaptiseq | 2 | 3.4±0.2 | 179.0 | .fastq.gz |

## Per-phase resource breakdown

| tool | phase | secs | CPU% mean/peak | RSS MB mean/peak | read MB/s | write MB/s | net recv MB/s |
|---|---|---|---|---|---|---|---|
| adaptiseq-classic | data | 4 | 11/16 | 38/38 | 0.00 | 64.09 | 64.39 |
| adaptiseq-classic | md5 | 2 | 8/13 | 43/48 | 0.00 | 49.69 | 49.71 |
| sra-toolkit | metadata | 10 | 1/5 | 29/30 | 0.00 | 0.00 | 0.01 |
| sra-toolkit | data | 39 | 14/72 | 31/31 | 0.00 | 15.88 | 16.03 |
| adaptiseq | data | 4 | 25/63 | 64/66 | 0.00 | 89.12 | 89.69 |
| adaptiseq | md5 | 2 | 1/1 | 71/74 | 0.00 | 0.01 | 0.06 |
