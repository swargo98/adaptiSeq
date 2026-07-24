#!/usr/bin/env bash
# Part 6 — provision a REAL IBM `ascp` (not the no-op benchmark stub) and the
# CURRENT ENA Aspera key, laid out exactly where adaptiSeq looks for them.
#
# What this does, and why each step matters:
#   1. Download the IBM Aspera Transfer SDK (ships a genuine linux-x86_64 `ascp`).
#   2. Extract `ascp` into a prefix whose `../etc` matches adaptiSeq's key search:
#         $(dirname ascp)/../etc/aspera/aspera_bypass_rsa.pem   (1st choice)
#         $(dirname ascp)/../etc/aspera_tokenauth_id_rsa        (2nd choice)
#   3. Install the `aspera-license` file the SDK `ascp` requires (decoded from the
#      aspera-cli data repository; the bare SDK does not ship it).
#   4. Install the ENA Aspera key.  IMPORTANT FINDING (2026-06): ENA migrated from
#      the legacy DSA key (`asperaweb_id_dsa.openssh`, shipped by Kingfisher and
#      older Aspera docs) to the **RSA** token-auth key.  The DSA key is now REJECTED
#      by fasp.sra.ebi.ac.uk (server returns "Permission denied (publickey)").  The
#      working key is the RSA key (`aspera_tokenauth_id_rsa`) — which is exactly the
#      2nd path adaptiSeq already checks, so no package code change is needed.
#   5. Put `ascp` on PATH via a symlink (resolve() follows it to the prefix, so the
#      `../etc` key discovery still resolves correctly).
#
# After running this, `which ascp` is real and
# `python3 -c "from adaptiseq.engine.classic import find_ena_aspera_key; print(find_ena_aspera_key())"`
# prints the RSA key.  Remove ~/.local/bin/ascp (symlink) and restore ascp.stub to
# go back to the benchmark stub.
set -euo pipefail

PFX="${ASPERA_PREFIX:-$HOME/.aspera/sdk}"
SDK_ZIP="${SDK_ZIP:-$HOME/.aspera/sdk.zip}"
ACLI_RAW="https://raw.githubusercontent.com/IBM/aspera-cli/main/lib/aspera/data"

mkdir -p "$PFX/bin" "$PFX/etc/aspera"

# 1. SDK (only if not already present)
if [[ ! -f "$SDK_ZIP" ]]; then
  echo "[setup] downloading IBM Aspera Transfer SDK (~160 MB)…"
  curl -sSL -o "$SDK_ZIP" "https://ibm.biz/aspera_sdk"
fi

# 2. ascp + libs
echo "[setup] extracting linux-x86_64 ascp…"
unzip -o -q "$SDK_ZIP" "linux-x86_64/*" -d "$HOME/.aspera/_sdk_extract"
cp "$HOME/.aspera/_sdk_extract/linux-x86_64/ascp" "$PFX/bin/ascp"
cp "$HOME/.aspera/_sdk_extract/linux-x86_64/"libstdc++.so.6* "$PFX/bin/" 2>/dev/null || true
chmod +x "$PFX/bin/ascp"

# 3. license (data item 6, zlib-deflated)  +  4. RSA key (data item 2, DER→PEM)
echo "[setup] fetching license + RSA key from aspera-cli data repository…"
curl -sSL -o /tmp/_asp_lic "$ACLI_RAW/6"
curl -sSL -o /tmp/_asp_rsa "$ACLI_RAW/2"
python3 - "$PFX" <<'PY'
import sys, zlib
from cryptography.hazmat.primitives.serialization import (
    load_der_private_key, Encoding, PrivateFormat, NoEncryption)
pfx = sys.argv[1]
open(f"{pfx}/etc/aspera-license", "wb").write(zlib.decompress(open("/tmp/_asp_lic","rb").read()))
rsa = load_der_private_key(open("/tmp/_asp_rsa","rb").read(), password=None)
pem = rsa.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
for name in (f"{pfx}/etc/aspera/aspera_bypass_rsa.pem", f"{pfx}/etc/aspera_tokenauth_id_rsa"):
    open(name, "wb").write(pem)
print("[setup] wrote license + RSA key (both adaptiSeq key paths)")
PY
chmod 600 "$PFX/etc/aspera/aspera_bypass_rsa.pem" "$PFX/etc/aspera_tokenauth_id_rsa"

# 5. on PATH (symlink; resolve() follows to the prefix for key discovery)
mkdir -p "$HOME/.local/bin"
[[ -e "$HOME/.local/bin/ascp" && ! -L "$HOME/.local/bin/ascp" ]] && \
  mv "$HOME/.local/bin/ascp" "$HOME/.local/bin/ascp.stub"
ln -sf "$PFX/bin/ascp" "$HOME/.local/bin/ascp"

echo "[setup] done."
"$PFX/bin/ascp" --version 2>&1 | grep -i "ascp version" || true
echo "[setup] ENA key: $(python3 -c 'from adaptiseq.engine.classic import find_ena_aspera_key as f; print(f())' 2>/dev/null || echo '?')"
