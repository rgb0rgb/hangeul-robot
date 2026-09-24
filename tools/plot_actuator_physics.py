"""Create an exportable plot from the recorded Gazebo controller output."""
import argparse
import csv
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    report = json.loads(args.report.read_text())
    folder = args.report.resolve().with_suffix("")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    for col, case in enumerate(("adequate", "insufficient")):
        with (folder / case / "commands.csv").open() as f:
            rows = [[float(v) for v in row] for row in list(csv.reader(f))[1:]]
        if not rows:
            raise ValueError(f"No controller samples for {case}")
        t = [r[0] - rows[0][0] for r in rows]
        cap = report["cases"][case]["model"]["parameters"]["torque_limit_nm"]
        axes[0, col].plot(t, [math.degrees(r[3]) for r in rows], label="Physics position")
        axes[0, col].plot(t, [math.degrees(r[2]) for r in rows], "--", label="Trajectory reference")
        axes[0, col].axhline(-10, color="gray", linestyle=":", label="Target (-10 deg)")
        axes[0, col].set_title(f"{case.capitalize()} torque: {cap:g} Nm limit")
        axes[0, col].set_ylabel("Angle (degrees)")
        axes[0, col].legend(fontsize=8)
        axes[1, col].plot(t, [r[1] for r in rows], color="tab:orange", label="Controller torque command")
        with (folder / case / "samples.csv").open() as f:
            states = [[float(v) for v in row] for row in list(csv.reader(f))[1:]]
        axes[1, col].plot([r[0] - rows[0][0] for r in states], [r[3] for r in states],
                          color="tab:green", label="Applied after limit")
        for bound in (-cap, cap):
            axes[1, col].axhline(bound, color="red", linestyle=":")
        axes[1, col].set_ylabel("Commanded torque (Nm)")
        axes[1, col].set_xlabel("Simulation time since observation start (s)")
        axes[1, col].legend(fontsize=8)
        for row in range(2):
            axes[row, col].grid(alpha=0.2)
    fig.suptitle("Hangeul Robot | Gazebo effort bench\nSynthetic parameters: 0.4 m link, 1 kg link + 1 kg payload; not a product test", fontsize=12)
    for ext in ("png", "svg"):
        fig.savefig(folder / f"comparison.{ext}", dpi=150)
    print(folder / "comparison.png")


if __name__ == "__main__":
    main()
