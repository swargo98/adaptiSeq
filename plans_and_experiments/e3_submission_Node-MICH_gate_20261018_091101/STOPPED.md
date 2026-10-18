# Gate stopped by hand, 2026-10-18 22:52 UTC

Panel 3r (one rep, six arms) completed; its rows in `e3_results.tsv` are valid.

Panel 3b was stopped during its first arm, fastq-dl, at the user's request (the
benchmark will be rerun on Expanse with changes). No 3b row was written. At the
stop, fastq-dl had been running 7 h 56 min (from 14:56:08) and had on disk 7 of
8 runs (both files each) plus 1,221,850,152 bytes of `SRR15852430_2.fastq.gz`:
25,042,319,401 bytes in total, about 0.88 MB/s. These files were not checked
against the manifest. Its log and concurrency trace are in `logs/`.

Processes were killed with SIGKILL and the payload directory was deleted.
