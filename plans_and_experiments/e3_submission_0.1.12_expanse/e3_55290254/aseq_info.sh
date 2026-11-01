#!/bin/bash
# The adaptiseq CLI with INFO-level logging (time-stamped), for diagnostic runs:
#   ASEQ_CLI=$PWD/bench/e3/aseq_info.sh sbatch --export=ALL bench/e3/e3_expanse.sbatch
# adaptiSeq does not configure logging, so normally only warnings reach the log.
exec python3 -c '
import logging, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
for noisy in ("asyncio", "aiohttp", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
from adaptiseq.cli import main
sys.exit(main(sys.argv[1:]))
' "$@"
