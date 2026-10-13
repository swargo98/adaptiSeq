# E8 — Fabric vs Expanse comparison (Fig 6 resource profile)

Cross-machine comparison of the E8 resource-profile run.
Sources: `e8_results_fabric/` (Node-FIU) and `e8_results_expanse/` (SDSC Expanse,
`exp-9-52`, job 52340455). This doc reads both TSVs; the per-machine analyses are
in each dir's `FINDINGS.md`.

## What differed in setup (control for it before comparing)

| | Fabric (Node-FIU) | Expanse (exp-9-52) |
|---|---|---|
| Cores / RAM | 8 / 62 GB | 128-core class / 32 GB requested |
| Reps | 3 | 5 |
| Python / psutil | (3.10) | 3.11.15 / 7.2.2 |
| Wall cap (timeout) | none hit | **1800 s** |
| 8-ENA file | **2.65 GB fastq.gz — same file** | **2.65 GB fastq.gz — same file** |
| 8-SRA accession | **SRR1031066** (544 MB→1.22 GB) | **SRR1031060** (200 MB→452 MB) |

**Directly comparable:** the 8-ENA panel (identical 2.65 GB payload) and the RSS/CPU
*fingerprints*. **Not directly comparable:** 8-SRA absolute numbers (different
accession/size) — compare the *pattern* there, not the magnitudes.

---

## 1. ENA throughput: Expanse is ~6–11× SLOWER (the headline)

Effective throughput on the identical 2.65 GB file (median):

| tool | Fabric wall / MB/s | Expanse wall / MB/s | Expanse slowdown |
|---|---|---|---|
| adaptiseq | 249 s / **10.7** | 1394–1786 s (2/5 done) / **~1.5–1.9** | ~5.6× |
| iseq | 735 s / **3.6** | 1800 s (0/5 done) / **<1.5** | ≥2.4× |
| kingfisher | 120 s / **22.1** | 1289 s / **2.1** | ~10.7× |

The counter-intuitive result: the **HPC node is far slower to EBI than the
commodity Fabric box.** Egress was *reachable* on both (Expanse's pre-flight got
200 OK), but bulk SDSC↔EBI throughput was ~1.5–2 MB/s vs Fabric's 3.6–22 MB/s.
Neither machine is "the fast one" in general — EBI throughput is a property of the
*path and time window*, exactly the master-plan §8/§13 caveat. On Fabric this same
run had its own slow window (see Fabric FINDINGS: a later probe saw ~61–73 MB/s);
Expanse's window was worse still.

## 2. Success rate flips on the slow link

Completion within the wall budget (ENA, 2.65 GB):

| tool | Fabric | Expanse |
|---|---|---|
| kingfisher | 3/3 | **5/5** |
| adaptiseq | 3/3 | **2/5** |
| iseq | 3/3 | **0/5** |

On Fabric everything finishes, so E8-ENA is a *speed* comparison. On Expanse's slow
link it becomes a *robustness* comparison, and the ordering by completion is
**kingfisher (aria2c single-flow) > adaptiseq (segmented aiohttp) > iseq
(single-stream FTP wget)**. iSeq's single wget stream cannot move 2.65 GB in 30 min
on a high-latency throttled path; aria2c's large-window single flow is the most
robust. This reproduces, at HPC scale, the Fabric "why kingfisher is fast" finding
(it's aria2c's single-flow TCP efficiency, not its 8 connections).

## 3. Resource *fingerprint* is consistent across machines (the robust result)

This is what E8 actually claims, and it transfers cleanly:

| metric (ENA) | Fabric | Expanse | verdict |
|---|---|---|---|
| peakRSS adaptiseq | 52 MB | 63 MB | **consistent** (single asyncio proc) |
| peakRSS iseq | 22 MB | 21 MB | **identical** (one wget child) |
| peakRSS kingfisher | 137 MB | 153 MB | **consistent** (aria2c -x8) |
| RSS ordering | king ≫ aseq ≫ iseq | king ≫ aseq ≫ iseq | **same** |
| mean_cpu ordering | king > aseq > iseq | king > aseq > iseq | **same** |

The RSS traces are flat and cleanly separated on both machines; the ~±15 MB drift
on the two larger tools is consistent with the longer Expanse runtime + psutil
7.2.2/py3.11. **mean_cpu% is lower on Expanse for every tool** (adaptiseq 12.7→2.6,
kingfisher 62.3→5.4) — a direct, interpretable consequence of the slower link
(fewer bytes/s → less compression/hashing work per second), not a different
execution model.

## 4. SRA panel: same pattern, magnitudes track the (different) accession

Different accessions, so compare structure:

| observation | Fabric (SRR1031066) | Expanse (SRR1031060) | verdict |
|---|---|---|---|
| convert balloon (aseq/iseq/king) | ~1.09–1.18 GB RSS | ~1.10–1.20 GB RSS | **same balloon** |
| prefetch stays lean | 10 MB / 5.6 core-s | 57 MB / 1.8 core-s | **same** (stops at .sra) |
| prefetch fastest | 14 s | 9 s | **same ranking** |
| adaptiseq/iseq rc=1 + valid output | yes | yes | **quirk reproduces** |
| cpu_core_s adaptiseq | 145.6 | 78.0 | tracks output size (1.22 GB vs 452 MB), **not machine** |
| peak convert CPU | ~800 % (8-core cap) | **~2900 %** (128-core node) | **machine-specific**: fasterq-dump fans out to available cores |

The one genuine *machine* effect on SRA: the 128-core node lets `fasterq-dump`
spike its convert threads much higher (peak ~29 cores vs Fabric's 8-core ceiling),
but **sustained** convert CPU (~2.5–3 cores) and therefore `cpu_core_s` are
governed by output bytes, not core count.

---

## Bottom line

| dimension | robust across machines? | notes |
|---|---|---|
| **Peak RSS / execution-model fingerprint** | ✅ yes | the E8 deliverable — reproduces exactly |
| **mean_cpu / cpu_core_s ordering** | ✅ yes | magnitudes scale with delivered byte-rate |
| **SRA convert balloon + prefetch-lean** | ✅ yes | format property, not machine |
| **adaptiseq/iseq rc=1 quirk** | ✅ yes | reproduces on both |
| **ENA wall-time / effective MB/s** | ❌ no | node-egress + time-of-day artefact (pre-registered) |
| **ENA completion / success rate** | ❌ no | flips with link speed (a robustness story, not a tool constant) |
| **peak_cpu_pct** | ❌ no | dominated by a t=0 startup transient + core count; use mean/∫ |

**For the paper:** report E8 as the *resource envelope* (RSS/CPU model, the SRA
conversion balloon, `cpu_core_s`) — verified to reproduce on two very different
machines. Do **not** report the ENA single-file wall-times as throughput; frame the
Expanse ENA result as evidence that **HPC egress to a specific archive can be the
bottleneck**, which is itself a useful systems finding and motivates adaptiSeq's
segmentation/adaptivity and the E9 link-saturation experiment. Single-file
throughput remains E2's job (aria2c wins single-file — pre-registered).
