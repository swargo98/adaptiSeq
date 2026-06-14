# adaptiSeq system benchmark — results

Per-second resource sampling of each tool's process tree, attributed to the four task phases (request / metadata / data / md5). `*_mbps` columns are **megabytes/s** (decimal MB). Net is system-wide.

## Headline (per run, mean ± sd)

| tool | runs | wall s | bytes MB | formats |
|---|---|---|---|---|
| iseq | 1 | 3.5±0.0 | 164.6 | .fastq.gz |
| sra-toolkit | 1 | 23.4±0.0 | 313.6 | .sra |
| adaptiseq | 1 | 3.4±0.0 | 164.6 | .fastq.gz |

## Per-phase resource breakdown

| tool | phase | secs | CPU% mean/peak | RSS MB mean/peak | read MB/s | write MB/s | net recv MB/s |
|---|---|---|---|---|---|---|---|
| iseq | data | 1 | 10/10 | 32/32 | 0.00 | 55.55 | 55.77 |
| iseq | md5 | 2 | 8/16 | 29/35 | 0.00 | 54.02 | 54.22 |
| sra-toolkit | metadata | 5 | 1/3 | 28/28 | 0.00 | 0.00 | 0.01 |
| sra-toolkit | data | 17 | 13/27 | 30/30 | 0.00 | 18.25 | 18.37 |
| sra-toolkit | md5 | 1 | 0/0 | 28/28 | 0.00 | 1.64 | 1.64 |
| adaptiseq | data | 2 | 27/53 | 69/78 | 0.00 | 81.88 | 82.39 |
| adaptiseq | md5 | 1 | 0/0 | 75/75 | 0.00 | 0.01 | 0.06 |
