# Train SmolVLA (8-joint ElRobot) on a university SLURM cluster

> **👋 Fresh Claude session on the server? This file is the single source of truth.**
> Read it top-to-bottom and you have everything: which repos to clone, where the dataset is, the
> mandatory 8-joint patch, the login-node → GPU-node flow, GPU tuning, and how to fetch the result.
> Two ready scripts sit next to this file: `prep_login.sh` (run on the login node) and
> `train_slurm.sh` (the GPU `sbatch` job). Just follow Phase 1 then Phase 2 below.

Full walkthrough, assuming nothing. Two phases: **login node** (internet + storage, no GPU)
does all the downloads; **compute node** (GPU) just trains.

## Your questions, answered
- **Clone norma-core?** Yes — the training code (`scripts/train.py`, the `smolvla/` package) lives in
  the **separate public repo** `github.com/norma-core/norma-core`. It is **not** in our repo.
- **Clone this repo too?** Yes — our repo holds the **dataset** (`datasets/dataset-cube*.parquet`, the
  17 episodes) plus these scripts. Clone **both**; order doesn't matter (the scripts do it for you).
- **Download a model first?** **No.** You're *training*, not running inference. `train.py` downloads the
  `lerobot/smolvla_base` model itself. (`prep_login.sh` pre-caches it so the GPU node works offline.)
  You'd only download a *trained* checkpoint if you wanted to run/resume one.
- **Is the dataset in GitHub?** Yes — the **17 source parquets** are committed (~356 MB). The merged
  file is **not** committed, and **you don't need it**: `--parquets` takes all 17 at once and
  concatenates them (stats over the full set). No merge step.
- **The 8-joint edit — is it on GitHub?** **No.** It was only an *uncommitted local change* in your WSL
  clone of norma-core (remote = norma-core's own repo, which we can't push to). A fresh clone has the
  **stock 6-dim** `train.py`. **Both scripts re-apply the patch with `sed`** → `STATE_DIM/ACTION_DIM = 8`.
- **What is `WORK`?** A working dir you choose where everything goes (repos, model cache, checkpoints).
  Home dirs are usually quota-limited → use scratch: `export WORK=/scratch/$USER/smolvla-train`.

## Phase 1 — on the LOGIN node (internet, storage)
```bash
# pick a dir with a few GB free (scratch, not quota-limited home)
export WORK=/scratch/$USER/smolvla-train

# get our repo (dataset + scripts), then run the prep
git clone https://github.com/Jaseelkt007/Robotics_berlin_hack.git "$WORK/Robotics_berlin_hack"
bash "$WORK/Robotics_berlin_hack/training/prep_login.sh"
```
`prep_login.sh` clones norma-core, patches train.py to 8-dim, installs `uv`, syncs the env (downloads
torch+CUDA), and pre-downloads the base models into `$WORK/hf-cache`. Run it once.

## Phase 2 — submit the GPU job to a COMPUTE node
First edit the `#SBATCH` lines in `training/train_slurm.sh` for **your** cluster (partition, account,
GPU). Then:
```bash
sbatch --export=ALL,WORK=$WORK "$WORK/Robotics_berlin_hack/training/train_slurm.sh"
```
It trains 15000 steps, **checkpoint every 2500** → `$WORK/checkpoints/cube-8dim/step-*/` and `final/`.
Watch progress: `tail -f smolvla-<jobid>.log`.

## Tuning for your GPU (RTX 6000)
- **48 GB card** → `--batch-size 48` (default in the script) or 64. **24 GB card** → drop to 24/32.
- `--lr 1e-4` pairs with ~batch 64 (NormaCore's default). If you cut batch hard, scale lr down
  (e.g. batch 16 → ~5e-5).
- Edit these directly in `train_slurm.sh` step 4.

## After training — get the model / run inference
```bash
ls $WORK/checkpoints/cube-8dim          # step-002500 ... step-015000, final
# confirm it's 8-dim:
grep action_dim $WORK/checkpoints/cube-8dim/final/config.json   # -> 8
```
Copy `final/` (or the best `step-*`) back to the robot machine and run `scripts/run_policy.py`
with `--motor-ids 1,2,3,4,5,6,7,8` (full arm + gripper).

## Gotchas
- **8-dim patch is mandatory** — without it you retrain the wrong (6-joint) shape. The scripts handle it.
- **No internet on the compute node?** That's why Phase 1 pre-caches everything into `$WORK` (shared
  filesystem). Just keep the **same `WORK`** in Phase 2.
- **Disk:** dataset ~356 MB + env ~5 GB + base model ~2 GB + checkpoints (~1.2 GB each). Use scratch.
