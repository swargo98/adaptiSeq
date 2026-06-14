#!/usr/bin/env bash
# Part 7 — provision NGDC/CNCB EdgeTurbo (the GSA download accelerator the iSeq paper
# benchmarks in Fig. 1D). GSA-only; daemon-based; the CLI status window needs a TTY
# (the sysbench edgeturbo adapter drives it under a pty).
#
# NOTE: from a host without working NGDC accelerated-transport connectivity the
# transfer stalls at 0% (observed from a US sandbox: daemon opens its UDP ports but
# no bytes move; ENA Aspera to EBI works fine from the same host). Run from an
# NGDC-reachable network (e.g. CN/CSTNET) to get real EdgeTurbo numbers.
set -euo pipefail

ETROOT="${ETROOT:-$HOME/.edgeturbo}"
URL="https://ngdc.cncb.ac.cn/ettrans/download/edgeturbo-client.linux.latest.cncb.tar.gz"

mkdir -p "$ETROOT"
echo "[setup] downloading EdgeTurbo linux client…"
curl -sSL -o "$ETROOT/edgeturbo.tar.gz" "$URL"
tar -zxf "$ETROOT/edgeturbo.tar.gz" -C "$ETROOT"
chmod +x "$ETROOT/edgeturbo-client/edgeturbo" "$ETROOT/edgeturbo-client/serv_edgeturbo"

# PATH wrapper (sets LD_LIBRARY_PATH to the bundled libstdc++/libgcc)
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/edgeturbo" <<EOF
#!/bin/bash
ETDIR="$ETROOT/edgeturbo-client"
export LD_LIBRARY_PATH="\$ETDIR/lib:\$LD_LIBRARY_PATH"
exec "\$ETDIR/edgeturbo" "\$@"
EOF
chmod +x "$HOME/.local/bin/edgeturbo"

echo "[setup] done — version:"
edgeturbo help 2>&1 | sed -n '2p' || true
echo "[setup] usage: edgeturbo start; edgeturbo set <dir>; edgeturbo dl /gsa/CRA.../CRR.../file"
