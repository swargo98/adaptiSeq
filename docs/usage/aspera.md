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

> **Note 3: the `ascp` must be recent**
> On 2026-11-12 ENA's Aspera server refused `ascp` 4.4.2, the one inside the conda
> package `aspera-cli` 4.14.0: it printed `ascp: failed to authenticate`, and its log
> said `SSH connection startup encountered invalid protocol`. `ascp` 4.4.8 (IBM Aspera Transfer SDK 1.1.9) transferred, and an
> adaptiSeq batch over it passed md5. Other versions were not tested. To get a current `ascp`:
>
> ```bash
> adaptiseq --install-ascp        # asks first; add --yes to confirm in a script
> ```
>
> It downloads the SDK from IBM's server and the public bypass key from IBM's `aspera-cli` repository,
> checks both against pinned sha256 values before writing anything, and installs them in `~/.aspera/sdk`
> (an older `~/.aspera/sdk` is kept as `sdk.old.<time>`). adaptiSeq then uses that `ascp` whenever it is
> newer than the one on `PATH`. From Python: `adaptiseq.install_ascp(assume_yes=True)`. The SDK is IBM
> software under IBM's terms, which the command reminds you of; adaptiSeq does not redistribute it.
>
> **Platforms.** The installer supports the two where the pinned SDK build was run against ENA: Linux
> x86_64, and macOS on Apple silicon (arm64; tested on macOS 26.2: `ascp` 4.4.8.2592 ran with no Gatekeeper
> prompt and transferred with the IBM bypass key). Intel Macs are not offered because the macOS x86_64 build
> could not be run on the machine available; on an Intel Mac, or on Windows or any other platform, install
> IBM Aspera Connect and put its `ascp` on `PATH`. On macOS `ascp` writes its logs, which include IP
> addresses, to `~/Library/Logs/Aspera`. On a macOS Python from python.org that cannot verify HTTPS
> certificates, run its `Install Certificates.command` (or `pip install certifi`) first.
>
> A failed ENA transfer prints which `ascp` ran and this advice.
>
> The `ascli` that conda's `aspera-cli` 4.14.0 provides (the tool ENA's
> [download page](https://ena-docs.readthedocs.io/en/latest/retrieval/file-download.html)
> recommends for fetching `ascp`) did not start in a fresh conda environment on 2026-11-12
> (`cannot load such file -- webrick`), so `--install-ascp` does not use it.

## Speed cap

`-s/--speed` (MB/s) applies to Aspera as well as the HTTP(S)/FTP engines.
