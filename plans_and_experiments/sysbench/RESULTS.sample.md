# adaptiSeq system benchmark — results

Per-second resource sampling of each tool's process tree, attributed to the four task phases (request / metadata / data / md5). `*_mbps` columns are **megabytes/s** (decimal MB). Net is system-wide.

## Headline (per run, mean ± sd)

| tool | runs | wall s | bytes MB | formats |
|---|---|---|---|---|
| iseq | 1 | 3.4±0.0 | 150.4 | .fastq.gz |
| sra-toolkit | 1 | 27.4±0.0 | 311.2 | .sra |
| pysradb | 1 | 5.0±0.0 | 0.0 |  |
| adaptiseq | 1 | 4.0±0.0 | 150.4 | .fastq.gz |

## Per-phase resource breakdown

| tool | phase | secs | CPU% mean/peak | RSS MB mean/peak | read MB/s | write MB/s | net recv MB/s |
|---|---|---|---|---|---|---|---|
| iseq | data | 1 | 8/8 | 32/32 | 0.00 | 50.92 | 51.22 |
| iseq | md5 | 2 | 9/17 | 32/36 | 0.00 | 49.30 | 49.41 |
| sra-toolkit | metadata | 6 | 1/5 | 28/28 | 0.00 | 0.00 | 0.02 |
| sra-toolkit | data | 20 | 12/26 | 30/30 | 0.00 | 15.48 | 15.72 |
| sra-toolkit | md5 | 1 | 1/1 | 28/28 | 0.00 | 0.00 | 1.65 |
| pysradb | metadata | 4 | 28/103 | 147/147 | 0.00 | 0.00 | 0.61 |
| adaptiseq | data | 2 | 16/32 | 62/64 | 0.00 | 39.99 | 44.63 |
| adaptiseq | md5 | 1 | 1/1 | 54/54 | 0.00 | 69.64 | 61.27 |
