# Hangeul Robot Public Edition

Hangeul Robot is a lightweight physical-AI runtime and robot operation console.
It models robots as replaceable parts, computes available capabilities from the current configuration,
and gates execution through safety and verification checks.

This public edition includes both **simulation and direct connection paths for supported hardware**.
It includes OpenManipulator-X and MyCobot 280 M5 adapters, so users can move real robots after
verifying ports, limits, and stop behavior on their own hardware.
It does not include customer-specific integrations or commercial operation tools.

## Getting started on Windows (no technical knowledge needed)

1. Click the green **Code** button above → **Download ZIP**.
2. Unzip it **somewhere permanent**, e.g. `C:\HangeulRobot` — not a folder you tidy up later such as
   Downloads, because the desktop shortcuts point here. Unzipping creates a `hangeul-robot-main`
   folder; the setup and launch files are **inside it**.
3. Double-click **`Setup.bat`** inside `hangeul-robot-main`. It installs Python if needed
   (internet required, a few minutes), downloads the dependencies, creates the desktop
   shortcuts **[한글 로봇]** (start) and **[한글 로봇 초기화]** (full reset), and starts.
4. When the browser opens, use **Add robot**. Plug the robot in over USB — the launcher
   finds it by its USB identity, so you do not need to know the COM number.

**When something goes wrong** — double-click **[한글 로봇 초기화]** (`Reset.bat`) or press
**Settings → Full reset & restart**. Everything is stopped, leftover blocks (disconnect
record, pause, device leases) are cleared, robots are found again and restarted, and you are
told what started and what did not, with the reason. **The emergency stop is never cleared** —
check the robot and press "Release stop" yourself.

**Good to know**

- **If you move or delete the folder**, the desktop shortcuts stop working. Run `Setup.bat` once
  more from the new location to recreate them.
- **`.bat` files inside a WSL folder (`\\wsl.localhost\...`) do not run when double-clicked** —
  the Windows command prompt cannot run from such network paths. Unzip to a Windows folder as above.
  For WSL, see "Run — Linux / WSL" below and [`install/windows/README.md`](install/windows/README.md).

## Included

| Item | Status |
|---|---|
| Console UI | Included |
| Module descriptor structure | Included |
| Capability calculation | Included |
| Configuration, verification, and safety gate concepts | Included |
| Simulated arm/hand/eye examples | Included |
| Public tests | Included |
| OpenManipulator-X adapter | Included |
| MyCobot 280 M5 adapter | Included |
| ROS 2 arm adapter (ros2_control) | Included · simulation only, physically unverified |
| Basic safety/current/temperature limit files | Included |
| Customer or commercial integrations | Excluded |

## ROS 2 arm — physically unverified

An `arm_ros2` adapter for the ros2_control JointTrajectoryController is included.
**It has been verified in simulation only; it has not been tested on physical actuators.**

| Stage | Result |
|---|---|
| Console → runtime → ROS 2 DDS → virtual joints (GenericSystem) | Connection, cancel, and error handling checked |
| Gazebo one-axis physics model (gravity, inertia, friction; 20 Nm / 2 Nm torque limits) | Reach vs. failure distinguished; failure is never shown as success |
| Physical robot | **Not verified** |

Machines without ROS 2 are unaffected (`rclpy` is imported only when this adapter is opened).
Details (Korean): [docs/ROS2_CONNECTION_AND_ACTUATOR_SIMULATION_20260921_KR.md](docs/ROS2_CONNECTION_AND_ACTUATOR_SIMULATION_20260921_KR.md),
[docs/ACTUATOR_PHYSICS_BENCH_20260921_KR.md](docs/ACTUATOR_PHYSICS_BENCH_20260921_KR.md)

## Run — Linux / WSL

On Ubuntu/WSL, install Python 3, pip and the `python3-venv` package first.
The installer creates a project-local `.venv`, including test dependencies.
Hardware packages are optional for simulation; installation failures are reported.

```bash
./install/install.sh
./run.sh        # start the console and a runtime for every registered robot
./restart.sh    # full reset and restart (the emergency stop is kept)
./stop.sh       # stop everything
```

Open `http://127.0.0.1:8099`.

All of these, the Windows `.bat` files and the "Full reset" button call `tools/launcher.py`.
It finds devices by the USB identity in the part descriptor (`usb_ids`) rather than by port
number, attaches USB devices to WSL with `usbipd` when needed, and writes what started and
what did not (with reasons) to `data/run/last_report.json`. Adding a robot in the console
starts its runtime.

**Simulation:** add a robot with the simulated arm (`arm_sim`) to read positions and test jog,
absolute and gripper moves without hardware. The demo joint range is 0–4095 ticks. The demo
arm and OMX share the default port 8601; register only one of them.

## Test

```bash
.venv/bin/python -m pytest -q
```

Verified in this prepared public folder:

```text
300 passed, 19 skipped
```

## Excluded features

Object/color tracking and arm-follow are not shipped. Their APIs report
`not_implemented`, and the UI does not poll them. `eye_sim` demonstrates the camera
interface only; it does not generate video frames (`read_frame()` returns `None`).

On Linux/WSL, `stop.sh` and `restart.sh` stop only servers started from this checkout.

## Safety Notice

This public edition can command supported physical robots when connected to hardware adapters.
The public edition is not a safety-certified industrial control system.
Always verify limits and stop behavior on your own hardware before enabling physical motion.

## License

Apache License 2.0
