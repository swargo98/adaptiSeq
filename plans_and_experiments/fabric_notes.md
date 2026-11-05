# Fabric half: notes and rows (branch `fabric-app-notes`)

Kept in this file, not in `remaining_tasks.md` or `progress_log.md`, so that `fabric-app-notes` and
`expanse-app-notes` merge without conflicts. Merge plan (user, 11-05): both branches are merged later into
one branch that holds the results; `main` gets only the updated software (`adaptiseq/`, `tests/`, docs),
not `plans_and_experiments/`. At the merge, fold this file's rows into `progress_log.md` section 1 and
delete the Fabric items from `remaining_tasks.md` item 3.

Files this branch adds or changes (all outside Expanse's edit paths): `bench/e3/run_submission.sh`,
`bench/e3/run_e3.sh` and `make_datasets.py` (panels 3rs/3bs, additive), `datasets/D?_scaled_*`,
`e3_submission_0.1.12_fabric/`, and this file. No change to `adaptiseq/`, the wheel or the env pins.

- **Status 2026-11-05 20:54: running.** Node `node1` (8 cores, 62 GB, payload on `/home/ubuntu/work/payload`, 965 GB
  free). IPv4 by hand (not persistent; redo after a reboot): `ip addr add 23.134.233.210/28 dev enp7s0`,
  `ip route add default via 23.134.233.209 dev enp7s0`, `ip -6 route add unreachable 2600:2701:5000:5001::/96`
  (FABNetv4Ext `net1`, CERN, assigned by the user). Env `adaptiseq_e3_sub` in `/home/ubuntu/work/envs`
  (Miniforge at `/home/ubuntu/work/miniforge3`; the pinned yml's pip section was installed by hand from
  `/home/ubuntu/work/pip_pins.txt`): iSeq 1.9.9, Kingfisher 0.5.0, fastq-dl 4.0.1, Python 3.11.17, wheel `0c5e6a82`.
- **Decision (user, 11-05): scaled panels.** ENA gave 0.2-0.5 MB/s per connection from this node (P=1 0.22-0.47,
  P=8 0.35-0.46, P=20 about 0.3; 3.5-6 MB/s total), so full 3r/3b would time out for the single-stream tools.
  Panels **3rs** (`D1_scaled_PRJNA916347`: 50 one-file + 10 three-file runs of D1_full, 1.84 GB) and **3bs**
  (`D2_scaled_PRJNA762469`: 2 of the 8 D2 runs, 6.46 GB), seed 20261105 set before any rep
  (`make_datasets.py`, `run_e3.sh`). Same arms, wheel, tool versions, `E3_SEED`; timeouts 10800 s and 30000 s.
  The user does not compare Fabric with Expanse (the paper compares tools and settings), so no Expanse rerun.
  Paper wording: Fabric used scaled panels because ENA's per-connection rate from that site was low.
- **Running:** `tmux` session `fabric`, `/home/ubuntu/work/run_fabric_reps.sh` (reps 1-5, one driver invocation each,
  status lines in `/home/ubuntu/work/fabric_reps.status`). Results `plans_and_experiments/e3_submission_0.1.12_fabric/e3_rep<r>/`
  (driver log `driver_rep<r>.log`). Restart one rep with `REP_LIST="3 4 5" tmux new -d -s fabric /home/ubuntu/work/run_fabric_reps.sh`.
  Per finished panel: `bash tools/check_panel.sh <rep dir> 3rs`, add rows to a "Fabric chain rows" table in
  `progress_log.md` section 1, commit. Not pushed yet (no GitHub credentials on this node checked; branch
  `fabric-app-notes`, local commits `7ca0dae` driver, `808fa47` scaled panels).
