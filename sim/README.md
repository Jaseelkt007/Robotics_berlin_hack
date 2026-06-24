# sim — run the trained SmolVLA policy in MuJoCo

A self-contained closed-loop inference test for the fine-tuned ElRobot pick-and-place policy.
Loads the URDF + scene, runs the trained checkpoint, lets you watch (or record) what the
model does.

## What you need on your machine

You already have **almost everything** if your layout looks like this:

```
<your-repo-root>/                    e.g. /mnt/d/normacore/
├── sim/                             ← this folder
│   ├── mujoco_eval.py
│   ├── requirements.txt
│   └── README.md
└── norma-core/                      ← already cloned next to the repo
    ├── hardware/elrobot/simulation/
    │   ├── elrobot_follower.urdf    ← used by the sim
    │   └── assets/                  ← STL meshes
    └── software/ai/smolvla_py/      ← the smolvla Python package
```

The only thing you don't have locally is the **trained checkpoint** — get it from
Hugging Face (see Setup step 4).

## Setup (one-time, ~10 minutes)

```bash
cd <your-repo-root>/sim

# 1) Python environment.
python3 -m venv .venv
source .venv/bin/activate

# 2) Install PyTorch. Pick ONE:
#    CPU-only (works anywhere, ~250 ms / forward — fine for sanity testing):
pip install torch
#    NVIDIA GPU with CUDA 12.1 (much faster, ~50 ms / forward):
# pip install torch --index-url https://download.pytorch.org/whl/cu121

# 3) Install the smolvla package (uses your sibling norma-core clone):
cd ../norma-core/software/ai/smolvla_py
pip install -e .
cd ../../../../sim

# 4) Install the rest of the runtime deps:
pip install -r requirements.txt

# 5) Download the trained checkpoint from Hugging Face (~1.2 GB):
mkdir -p checkpoint
huggingface-cli download captainjaseel/smolvla-cube-8dim-v2 --local-dir checkpoint
ls checkpoint/    # should show: config.json, model.safetensors, stats.safetensors
```

## Run it

### Quick smoke (no display needed — save MP4 and open it in Windows)

```bash
python mujoco_eval.py --steps 100 --video out.mp4
# Open D:\normacore\sim\out.mp4 in VLC / Movies & TV
```

### Interactive 3D viewer (needs WSLg — Windows 11 has it built in)

```bash
python mujoco_eval.py --steps 300
# Native MuJoCo viewer window opens. Mouse-drag to rotate, scroll to zoom.
```

### Longer rollout / different prompt / different cube position

```bash
python mujoco_eval.py \
    --steps 600 \
    --inner-steps 5 \
    --task "pick up the black object" \
    --video long.mp4
```

## What to expect from run #1 (be honest with yourself)

This is the first time the model — trained on real-world camera images of your physical
ElRobot — meets a sim that we built from scratch (workspace, lighting, camera angles all
approximations). Realistic outcomes:

| What you see | What it means |
|---|---|
| Arm doesn't move at all | Model loaded but predicts ≈ current state. Sometimes happens; check action scale. |
| Arm moves wildly / waves | Camera viewpoint too far from training; model has no idea what it's seeing. |
| Arm makes plausible motion toward something | Viewpoints / colors are close — tune `cam1` pose in `mujoco_eval.py`. |
| Arm reaches and grips the cube | 🎉 Strong sign the model generalized well. |

A first run that produces **plausible-looking motion** counts as success. We iterate from there
by tweaking camera pose, object positions, and lighting until the sim render starts looking
more like the training images.

## Tweaking after run #1

Open `mujoco_eval.py`, look for `SCENE_TEMPLATE`, and edit:

- `<camera name="cam1" pos="…" xyaxes="…"/>` — controls the third-person view. Move it around until the rendered cam1 image roughly matches the training-set side photo (check `assets/training_images/cam1_sample.png` if you grabbed those from the bundle).
- `<body name="black_cube" pos="…">` — move the cube to roughly where it was in your training data.
- `<body name="green_box" pos="…">` — same for the target container.

Re-run after each tweak. The script is fast to iterate.

## How it works (one paragraph)

For each outer step the script renders two 224×224 RGB frames (cam0, cam1) from MuJoCo,
reads the 8 joint angles from `data.qpos`, converts radians → `position_norm ∈ [0,1]` using
the URDF joint limits, z-score normalizes against `stats.safetensors`, feeds everything plus
the task prompt into `SmolVLAPolicy.predict_action_chunk`, takes the first predicted action,
un-normalizes it back to radians, sets `data.ctrl[:8]`, and steps physics 10 sub-steps.
Repeat. The checkpoint, the URDF, and the workspace fully determine what you'll see.
