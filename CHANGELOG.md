# 0.3.0 — Windows one-click setup, full reset, repeat work (2026-09-24)

- **Windows one-click setup.** `Setup.bat` installs Python when missing (winget), creates `.venv`,
  installs dependencies, adds desktop shortcuts and starts. `Start.bat`, `Reset.bat`, `Stop.bat`.
- **One launcher for start / full reset / stop** (`tools/launcher.py`). `run.sh`, `restart.sh`,
  `stop.sh`, the `.bat` files and the console's "Full reset & restart" button all use it.
  It starts a runtime for every registered robot, finds devices by USB identity (`usb_ids` in the
  part descriptor) instead of port number, attaches USB to WSL with `usbipd` when needed, stops
  only this checkout's processes, clears stale disconnect/pause/lease state (**never the emergency
  stop**), and reports what started and what did not, with reasons.
- The console's restart now waits for the result, shows it and reloads. Previously the public
  `run.sh` started only the console, so pressing restart **removed the runtimes**.
- Adding a robot in the console starts its runtime.
- Runtime: fixed startup on Windows (`st_rdev` does not exist there); a device that disappears and
  comes back — even under the same COM name or a different `ttyUSB` number — is reopened without
  a restart; while it is missing, the error says so instead of a Python `NoneType` message.
- **Repeat work mode:** move one joint or the gripper between A and B a set number of times, with
  dwell times; save it as a single movement card and use it in sequences. Sequence cancel / pause /
  resume now reach the running sequence (they previously only changed the display).
- The save dialog scrolls inside itself on short screens (the save button was unreachable at 720px).
- Add a ROS 2 arm adapter (`arm_ros2`, ros2_control JointTrajectoryController) with a bounded
  transport: fresh joint states, action feedback/result/cancel, and stale-state refusal.
- Add ROS 2 connection and one-axis Gazebo actuator physics verification tools, a torque-limit
  plugin, and the recorded evidence.
- ROS 2: **verified in simulation only. Not yet tested on physical actuators.**

# 0.2.1 — Public runtime fixes (2026-09-17)

- Make the documented simulation command instantiate a virtual arm and hand.
- Preserve ESTOP and configured range checks; mark simulated moves as non-hardware.
- Return explicit unsupported results for excluded tracking APIs and stop their UI polling.
- Show runtime connection errors in motion controls.
- Install runtime and test dependencies in a project-local virtual environment.
- Limit stop/restart to server processes in the current checkout.
- Add API and UI regression coverage for these paths.

# Changelog

## 0.2.0-public-real

- Prepared a public release with simulation and supported physical hardware paths.
- Included the console UI, runtime contracts, module descriptors, and public tests.
- Added simulated arm and camera adapters.
- Included OpenManipulator-X and MyCobot 280 M5 adapters with safety limit files.
- Excluded logs, private robot instances, customer-specific material, and commercial operation tools.
