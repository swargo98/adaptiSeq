# Aspera (`-a`)

Use IBM Aspera (`ascp`) for high-speed transfer.

```bash
adaptiseq -i PRJNA211801 -a -g
```

Aspera is **opt-in** and supported for **GSA / ENA only** — the NCBI **SRA**
database does not offer Aspera, so adaptiSeq downloads SRA files over HTTPS
instead.

## Adaptive parallel Aspera (ENA)

`ascp` cannot pause/resume mid-file, so the gradient batch controller (which
pauses and re-queues files) does not apply. Instead, with `-a` adaptiSeq runs a
parallel `ascp` pool gated at **file-pickup boundaries**, tuned by an
**additive-increase + efficiency-hysteresis** controller:

1. Measure single-worker throughput (baseline).
2. Each interval, tentatively add one worker.
3. Keep it only if aggregate throughput reaches at least `--aspera-efficiency`
   (default **0.70**) of `workers × baseline`; otherwise drop it and hold (no
   flapping).

Because `ascp` writes bytes out-of-process, throughput is measured by sampling
output-directory growth.

```bash
adaptiseq -i ena_list.txt -a --aspera-efficiency 0.8
```

This path is **validated against the real ENA Aspera endpoint** with a genuine IBM
`ascp`: single-file and multi-file batches transfer and pass md5, and the
controller correctly backs off to one session when ENA throttles a second
concurrent `ascp`.

## GSA Aspera

GSA Aspera is supported on a **sequential, best-effort** basis. The Huawei-Cloud
preference rule: when a Huawei-Cloud link is available
adaptiSeq prefers it (faster/more stable) **even with `-a`**, so `-a` is still
recommended for GSA as a fast fallback. GSA Aspera has **not yet** been validated
against the live endpoint here.

## Requirements

> **Note 1**
> `-a` requires a real IBM `ascp` on `PATH`. A no-op stub will pass startup checks
> but transfer nothing.

> **Note 2**
> Aspera needs a key file. adaptiSeq searches the conda environment and
> `~/.aspera` automatically. ENA migrated its Aspera auth from DSA to RSA keys;
> the legacy `asperaweb_id_dsa.openssh` is now rejected, but adaptiSeq's RSA
> fallback covers it.

## Speed cap

`-s/--speed` (MB/s) applies to Aspera as well as the HTTP(S)/FTP engines.
