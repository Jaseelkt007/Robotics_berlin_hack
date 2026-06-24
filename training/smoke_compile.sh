#!/bin/bash
# =====================================================================
# Train SmolVLA (8-joint ElRobot) on a SLURM university cluster.
# Submit from the LOGIN node:   sbatch training/train_slurm.sh
# (Edit the #SBATCH lines for YOUR cluster: partition / account / GPU name.)
# =====================================================================
#SBATCH --job-name=smolvla-compile-smoke
#SBATCH --partition=highperf
#SBATCH --gres=gpu:rtx_a6000:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=64G
#SBATCH --time=00:45:00
#SBATCH --output=/no_backups/s1492/smolvla-train/logs/smoke-compile-%j.log

set -eo pipefail

# ---------------------------------------------------------------------
# 0. Paths — point WORK at a scratch/work dir with a few GB free.
# ---------------------------------------------------------------------
WORK="${WORK:-$HOME/smolvla-train}"
NORMA="$WORK/norma-core"                              # training CODE (upstream)
DATA="$WORK/Robotics_berlin_hack"                     # OUR repo (dataset + this script)
OUT="$WORK/checkpoints/cube-8dim-smoke-compile"                     # checkpoints land here
export HF_HOME="$WORK/hf-cache"                       # base model cache (shared login+compute)
export UV_CACHE_DIR="$WORK/uv-cache"                  # keep uv cache off the quota-limited home
export HF_HUB_OFFLINE=1                               # compute node has no internet — use cached models
export WANDB_PROJECT="smolvla-elrobot-cube"
export WANDB_ENTITY="jaseelkt1-university-of-stuttgart"
export WANDB_NAME="smoke-compile-${SLURM_JOB_ID:-local}"
export SMOLVLA_ATTN_IMPL=sdpa
export SMOLVLA_COMPILE=1
export SMOLVLA_COMPILE_MODE=default
export WANDB_DIR="$WORK/logs"
export WANDB_MODE="${WANDB_MODE:-online}"             # highperf nodes have outbound net (Ctrl-V job confirms)
mkdir -p "$WORK" "$OUT" "$HF_HOME" "$WORK/logs"

# ---------------------------------------------------------------------
# 1. Get the code (norma-core) and the dataset (our repo).
# ---------------------------------------------------------------------
[ -d "$NORMA" ] || git clone --depth 1 https://github.com/norma-core/norma-core.git "$NORMA"
[ -d "$DATA" ]  || git clone --depth 1 https://github.com/Jaseelkt007/Robotics_berlin_hack.git "$DATA"

# ---------------------------------------------------------------------
# 2. CRITICAL: patch train.py to 8 joints (upstream ships 6 for the SO-101).
#    Your ElRobot is 8-DoF; without this the model trains on the wrong shape.
# ---------------------------------------------------------------------
TRAIN="$NORMA/software/ai/smolvla_py/scripts/train.py"
sed -i 's/^STATE_DIM = 6$/STATE_DIM = 8/; s/^ACTION_DIM = 6$/ACTION_DIM = 8/' "$TRAIN"
echo "train.py dims now:"; grep -E '^(STATE|ACTION)_DIM' "$TRAIN"   # must read 8 / 8

# ---------------------------------------------------------------------
# 3. Install uv (no root) + sync the exact training env (CUDA torch).
# ---------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
cd "$NORMA/software/ai/smolvla_py"
uv sync --offline || uv sync

# ---------------------------------------------------------------------
# 4. Train — pass all 17 parquets straight to --parquets (it concatenates
#    them and computes stats over the full set; NO separate merge needed).
#    RTX 6000 (48GB) -> batch 48-64; if it's a 24GB card, drop to 24/32.
#    lr pairs with batch (NormaCore default lr 1e-4 @ batch 64).
# ---------------------------------------------------------------------
PYTHONUNBUFFERED=1 uv run python scripts/train.py \
  --steps 300 \
  --save-every 9999 \
  --decay-steps 300 \
  --batch-size 48 \
  --num-workers 12 \
  --lr 1e-4 \
  --log-every 20 \
  --parquets "$DATA"/datasets/dataset-cube*.parquet \
  --output "$OUT" \
  --wandb-project "$WANDB_PROJECT" \
  --wandb-entity "$WANDB_ENTITY" \
  --wandb-run-name "$WANDB_NAME"

echo "DONE — checkpoints in $OUT (step-*/, final/)"
