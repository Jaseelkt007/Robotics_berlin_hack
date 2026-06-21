"""Parse a train.py stdout log into lr/loss curves (CSV always; PNG if matplotlib present).

train.py prints one line per --log-every:
    step    100/15000  loss 1.2345  lr 7.55e-05  (3.21 step/s)

Usage:
    uv run python scripts/plot_lr.py --log train.log --out checkpoints/cube-run
-> writes <out>/lr_curve.csv  and  <out>/lr_curve.png  (step,lr,loss)
"""
import argparse
import csv
import re
from pathlib import Path

LINE = re.compile(r"step\s+(\d+)/\d+\s+loss\s+([\d.]+)\s+lr\s+([\d.eE+-]+)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, required=True, help="train.py stdout log (from | tee)")
    ap.add_argument("--out", type=Path, required=True, help="output dir (checkpoint dir is fine)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for ln in a.log.read_text(errors="ignore").splitlines():
        m = LINE.search(ln)
        if m:
            rows.append((int(m.group(1)), float(m.group(3)), float(m.group(2))))  # step, lr, loss
    if not rows:
        print("No 'step .. loss .. lr ..' lines found — is this a train.py log?")
        return

    csv_path = a.out / "lr_curve.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "lr", "loss"])
        w.writerows(rows)
    print(f"wrote {csv_path}  ({len(rows)} points)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib not installed -> CSV only. `uv pip install matplotlib` for the PNG.")
        return

    steps = [r[0] for r in rows]
    lrs = [r[1] for r in rows]
    losses = [r[2] for r in rows]
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(steps, lrs, color="tab:blue", label="lr")
    ax1.set_xlabel("step"); ax1.set_ylabel("learning rate", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(steps, losses, color="tab:red", alpha=0.6, label="loss")
    ax2.set_ylabel("loss", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    fig.suptitle("SmolVLA training — LR & loss")
    fig.tight_layout()
    png = a.out / "lr_curve.png"
    fig.savefig(png, dpi=120)
    print(f"wrote {png}")


if __name__ == "__main__":
    main()
