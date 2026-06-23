#!/bin/bash
# =====================================================================
# RUN THIS ON THE LOGIN NODE (has internet + storage, no GPU needed).
# Does every internet-dependent step up front, so the GPU compute node
# can train fully offline afterwards.
#   1. clone the training code (norma-core) + the dataset (our repo)
#   2. patch train.py to 8 joints (upstream ships 6 — your edit isn't on GitHub)
#   3. install uv + sync the env (downloads torch + CUDA wheels)
#   4. pre-download the SmolVLA base models into the shared HF cache
#
# Usage (login node):
#   export WORK=/scratch/$USER/smolvla-train      # a dir with a few GB free
#   bash training/prep_login.sh
# =====================================================================
set -eo pipefail

WORK="${WORK:-$HOME/smolvla-train}"
NORMA="$WORK/norma-core"
DATA="$WORK/Robotics_berlin_hack"
export HF_HOME="$WORK/hf-cache"                 # base-model cache (shared with the GPU node)
mkdir -p "$WORK" "$HF_HOME"
echo "WORK = $WORK"

# 1. code + dataset
[ -d "$NORMA" ] || git clone --depth 1 https://github.com/norma-core/norma-core.git "$NORMA"
[ -d "$DATA" ]  || git clone --depth 1 https://github.com/Jaseelkt007/Robotics_berlin_hack.git "$DATA"

# 2. 8-joint patch (your local edit is NOT on GitHub — re-apply it here)
TRAIN="$NORMA/software/ai/smolvla_py/scripts/train.py"
sed -i 's/^STATE_DIM = 6$/STATE_DIM = 8/; s/^ACTION_DIM = 6$/ACTION_DIM = 8/' "$TRAIN"
echo "train.py dims:"; grep -E '^(STATE|ACTION)_DIM' "$TRAIN"     # must be 8 / 8

# 3. uv + env
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
cd "$NORMA/software/ai/smolvla_py"
uv sync

# 4. pre-fetch base models into HF_HOME (so the GPU node needs no internet)
uv run python - <<'PY'
from huggingface_hub import snapshot_download
for repo in ["lerobot/smolvla_base", "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"]:
    print("fetching", repo, "...")
    snapshot_download(repo)
print("base models cached.")
PY

echo
echo "LOGIN PREP DONE."
echo "Now submit the GPU job (set the SAME WORK):"
echo "    sbatch --export=ALL,WORK=$WORK $DATA/training/train_slurm.sh"
