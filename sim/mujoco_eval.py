"""MuJoCo closed-loop inference for the SmolVLA cube checkpoint.

Loads the ElRobot URDF, builds a workspace (table + black cube + green box),
and runs the trained policy in a loop: render -> infer -> step physics -> repeat.

Usage:
    python mujoco_eval.py                        # interactive window (needs display)
    python mujoco_eval.py --video out.mp4        # save MP4 instead of window
    python mujoco_eval.py --steps 250 --video out.mp4

Defaults assume the bundle layout produced by `prep_bundle.sh` on the cluster:

    sim_bundle/
      assets/
        elrobot_follower.urdf
        assets/ (meshes referenced by the URDF)
      checkpoint/
        config.json model.safetensors stats.safetensors
      scripts/
        mujoco_eval.py   <-- you are here
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import mujoco
from safetensors.torch import load_file as load_safetensors


# ----- joint range constants pulled from elrobot_follower.urdf -----
# (lower, upper) in radians per joint, indexed 0..7
JOINT_LIMITS = [
    (-1.5509, 1.5509),   # rev_motor_01  base yaw
    (-1.6122, 1.6122),   # rev_motor_02  shoulder pitch
    (-1.7610, 1.7610),   # rev_motor_03  elbow
    (-1.7533, 1.7533),   # rev_motor_04
    (-2.6200, 3.2520),   # rev_motor_05  wrist
    (-1.3775, 1.7641),   # rev_motor_06
    (-3.2014, 2.7336),   # rev_motor_07
    (0.0000,  2.2028),   # rev_motor_08  gripper
]


# ----- normalization helpers (mirror smolvla.normalize) -----
def norm_to_rad(norm: np.ndarray) -> np.ndarray:
    """[0,1] per-joint -> radians using URDF limits."""
    lows = np.array([lo for lo, _ in JOINT_LIMITS], dtype=np.float32)
    highs = np.array([hi for _, hi in JOINT_LIMITS], dtype=np.float32)
    return lows + norm.clip(0.0, 1.0) * (highs - lows)


def rad_to_norm(rad: np.ndarray) -> np.ndarray:
    """Radians per-joint -> [0,1] using URDF limits."""
    lows = np.array([lo for lo, _ in JOINT_LIMITS], dtype=np.float32)
    highs = np.array([hi for _, hi in JOINT_LIMITS], dtype=np.float32)
    return ((rad - lows) / (highs - lows)).clip(0.0, 1.0)


# ----- the workspace scene -----
# Wraps the URDF and adds: floor, table, black cube, green box, two cameras.
# cam0 = eye-in-hand (attached to the gripper link via the URDF parser).
# cam1 = fixed third-person, roughly matching the training-data side viewpoint.
SCENE_TEMPLATE = """
<mujoco model="elrobot_cube_scene">
  <compiler meshdir="{asset_dir}" angle="radian"/>

  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicit"/>

  <visual>
    <global offwidth="224" offheight="224"/>
    <quality shadowsize="2048"/>
    <map force="0.1" zfar="30"/>
  </visual>

  <asset>
    <texture type="2d" name="wood" builtin="flat" rgb1="0.78 0.65 0.42" width="512" height="512"/>
    <material name="wood_mat" texture="wood" texrepeat="4 4" specular="0.0"/>
    <material name="black_mat" rgba="0.05 0.05 0.05 1"/>
    <material name="green_mat" rgba="0.10 0.65 0.20 1"/>
  </asset>

  <include file="{urdf_file}"/>

  <worldbody>
    <light name="overhead" pos="0 0 1.8" dir="0 0 -1" diffuse="0.7 0.7 0.7"/>
    <light name="fill"    pos="0.6 0.6 1.2" dir="-0.5 -0.5 -1" diffuse="0.3 0.3 0.3"/>

    <geom name="floor"    type="plane"  size="2 2 0.05" material="wood_mat" pos="0 0 0"/>

    <!-- The black object the model should pick. Placed in front of the arm, on the table. -->
    <body name="black_cube" pos="0.18 0.05 0.022">
      <freejoint/>
      <geom name="black_cube" type="box" size="0.018 0.018 0.018" material="black_mat" mass="0.05"
            friction="1.0 0.05 0.001"/>
    </body>

    <!-- The green container the model should place INTO. -->
    <body name="green_box" pos="-0.18 0.05 0.020">
      <geom name="green_box_bottom" type="box" size="0.05 0.04 0.005" material="green_mat" pos="0 0 0"/>
      <geom name="green_box_w1"     type="box" size="0.05 0.005 0.025" material="green_mat" pos="0 0.035 0.025"/>
      <geom name="green_box_w2"     type="box" size="0.05 0.005 0.025" material="green_mat" pos="0 -0.035 0.025"/>
      <geom name="green_box_w3"     type="box" size="0.005 0.04 0.025" material="green_mat" pos="0.045 0 0.025"/>
      <geom name="green_box_w4"     type="box" size="0.005 0.04 0.025" material="green_mat" pos="-0.045 0 0.025"/>
    </body>

    <!-- cam1: third-person side view (rough match to training cam1 image). -->
    <camera name="cam1" pos="0.0 0.55 0.45" mode="fixed"
            xyaxes="-1 0 0  0 -0.6 0.8"/>

    <!-- cam0: eye-in-hand camera attached to the gripper.
         The URDF defines the gripper link; cam0 is attached at its tip.
         We can't add a child <camera> to a URDF body via include, so this camera
         is positioned via a worldspace fallback that approximates the gripper view.
         For accurate eye-in-hand rendering, attach to the gripper body in Python. -->
    <camera name="cam0_fallback" pos="0.0 0.0 0.45" mode="targetbody" target="black_cube"/>
  </worldbody>

  <!-- Position actuators on each motor joint (PD control with target = ctrl). -->
  <actuator>
    <position name="act_01" joint="rev_motor_01" kp="50" ctrlrange="-1.5509  1.5509"/>
    <position name="act_02" joint="rev_motor_02" kp="50" ctrlrange="-1.6122  1.6122"/>
    <position name="act_03" joint="rev_motor_03" kp="50" ctrlrange="-1.7610  1.7610"/>
    <position name="act_04" joint="rev_motor_04" kp="50" ctrlrange="-1.7533  1.7533"/>
    <position name="act_05" joint="rev_motor_05" kp="30" ctrlrange="-2.6200  3.2520"/>
    <position name="act_06" joint="rev_motor_06" kp="30" ctrlrange="-1.3775  1.7641"/>
    <position name="act_07" joint="rev_motor_07" kp="30" ctrlrange="-3.2014  2.7336"/>
    <position name="act_08" joint="rev_motor_08" kp="20" ctrlrange="0       2.2028"/>
  </actuator>
</mujoco>
"""


def build_model(urdf_path: Path) -> mujoco.MjModel:
    urdf_path = urdf_path.resolve()
    if not urdf_path.exists():
        sys.exit(f"URDF not found at {urdf_path}. Use --urdf to point at the right path.")
    asset_dir = urdf_path.parent / "assets"
    xml = SCENE_TEMPLATE.format(
        asset_dir=str(asset_dir),
        urdf_file=str(urdf_path),
    )
    scene_path = urdf_path.parent / "_composed_scene.xml"
    scene_path.write_text(xml)
    return mujoco.MjModel.from_xml_path(str(scene_path))


# ----- model loading (uses the smolvla package from the bundle) -----
def load_policy(ckpt_dir: Path, device: torch.device):
    """Load the trained SmolVLA policy and its stats."""
    # The smolvla package must be importable. We assume the bundle either
    # ships it under the venv (pip install) or that the user has cloned norma-core.
    try:
        from smolvla import SmolVLAPolicy
    except ImportError as e:
        sys.exit(
            "Cannot import smolvla. Install it via:\n"
            "  cd <bundle>/smolvla_py && pip install -e .\n"
            f"(original error: {e})"
        )

    print(f"Loading checkpoint from {ckpt_dir} ...")
    policy = SmolVLAPolicy.from_pretrained(str(ckpt_dir), strict=False).to(device).eval()
    stats = load_safetensors(str(ckpt_dir / "stats.safetensors"))
    stats = {k: v.to(device) for k, v in stats.items()}
    return policy, stats


def render_camera(model: mujoco.MjModel, data: mujoco.MjData, cam_name: str,
                  renderer: mujoco.Renderer) -> torch.Tensor:
    """Render a 224x224 RGB frame from the named camera. Returns (3, H, W) float in [0, 1]."""
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, cam_name)
    if cam_id < 0:
        # Camera not found — use a default fallback.
        cam_id = 0
    renderer.update_scene(data, camera=cam_id)
    rgb = renderer.render()  # (H, W, 3) uint8
    img = torch.from_numpy(rgb.copy()).permute(2, 0, 1).float() / 255.0
    return img


def build_batch(state_rad: np.ndarray,
                cam0_img: torch.Tensor, cam1_img: torch.Tensor,
                task: str,
                policy, stats, device) -> dict:
    """Mirror smolvla.dataset.PickAndPlaceDataset + train.build_train_batch."""
    state_norm = rad_to_norm(state_rad)                          # (8,) in [0, 1]
    state_t = torch.from_numpy(state_norm.astype(np.float32)).unsqueeze(0).to(device)

    from smolvla.normalize import normalize_state
    state_t = normalize_state(state_t, stats)

    batch = {
        "observation.state": state_t,
        "observation.images.cam0": cam0_img.unsqueeze(0).to(device),
        "observation.images.cam1": cam1_img.unsqueeze(0).to(device),
    }
    tokens, mask = policy.tokenize_task([task], device=device)
    batch["observation.language.tokens"] = tokens
    batch["observation.language.attention_mask"] = mask
    return batch


def main():
    here = Path(__file__).resolve().parent
    # Default paths assume layout: <repo>/sim/mujoco_eval.py + <repo>/norma-core/...
    default_urdf = here.parent / "norma-core" / "hardware" / "elrobot" / "simulation" / "elrobot_follower.urdf"
    default_ckpt = here / "checkpoint"

    ap = argparse.ArgumentParser()
    ap.add_argument("--urdf", type=Path, default=default_urdf,
                    help=f"Path to elrobot_follower.urdf (default: {default_urdf})")
    ap.add_argument("--ckpt", type=Path, default=default_ckpt,
                    help=f"Path to checkpoint directory (default: {default_ckpt})")
    ap.add_argument("--task", type=str, default="put the black object inside the green box",
                    help="Language prompt fed to the policy.")
    ap.add_argument("--steps", type=int, default=300,
                    help="Number of outer policy steps (each step applies the first action of the predicted chunk).")
    ap.add_argument("--inner-steps", type=int, default=10,
                    help="Physics steps per outer step (controls smoothness).")
    ap.add_argument("--video", type=Path, default=None,
                    help="If set, write an MP4 of cam1 to this path instead of opening a viewer.")
    ap.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    urdf_path = args.urdf.resolve()
    ckpt_dir = args.ckpt.resolve()
    device = torch.device(args.device)

    print(f"URDF:       {urdf_path}")
    print(f"Checkpoint: {ckpt_dir}")
    print(f"Device:     {device}")

    model = build_model(urdf_path)
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=224, width=224)

    # Bring the arm to a neutral start. Zero pose is a reasonable default;
    # tune via this dict if you have a recorded "home" pose for your arm.
    data.qpos[:8] = 0.0
    mujoco.mj_forward(model, data)

    policy, stats = load_policy(ckpt_dir, device)

    # Optional: video writer.
    writer = None
    if args.video is not None:
        try:
            import imageio.v2 as imageio
            writer = imageio.get_writer(str(args.video), fps=30)
            print(f"Writing video to {args.video}")
        except ImportError:
            sys.exit("imageio not installed. `pip install imageio[ffmpeg]`")

    print(f"\nStarting closed-loop sim. Task: {args.task!r}")
    t0 = time.time()
    for outer in range(args.steps):
        cam0_img = render_camera(model, data, "cam0_fallback", renderer)
        cam1_img = render_camera(model, data, "cam1", renderer)

        state_rad = data.qpos[:8].astype(np.float32)
        batch = build_batch(state_rad, cam0_img, cam1_img, args.task, policy, stats, device)

        with torch.no_grad():
            action_chunk = policy.predict_action_chunk(batch)         # (1, chunk, 8) normalized
        from smolvla.normalize import unnormalize_action
        action_chunk = unnormalize_action(action_chunk, stats)        # (1, chunk, 8) in [0, 1]
        first_action = action_chunk[0, 0].cpu().numpy()               # (8,)
        target_rad = norm_to_rad(first_action)
        data.ctrl[:8] = target_rad

        for _ in range(args.inner_steps):
            mujoco.mj_step(model, data)

        if outer % 20 == 0:
            dt = time.time() - t0
            print(f"  step {outer:>4}/{args.steps}   cube_z={data.body('black_cube').xpos[2]:.3f}m   "
                  f"({(outer+1)/max(dt,1e-9):.1f} step/s)")

        if writer is not None:
            renderer.update_scene(data, camera=mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "cam1"))
            writer.append_data(renderer.render())

    if writer is not None:
        writer.close()
        print(f"Wrote {args.video}")
    else:
        # Open the interactive viewer.
        with mujoco.viewer.launch_passive(model, data) as viewer:
            print("Viewer open. Ctrl-C to quit.")
            while viewer.is_running():
                mujoco.mj_step(model, data)
                viewer.sync()


if __name__ == "__main__":
    main()
