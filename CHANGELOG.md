# 0.4.2 — Resume after pause actually resumes (2026-10-19)

- Pressing Resume after Pause now continues the run. Before, nothing ever told the runtime
  to leave the paused state, and a running repeat motion counted the move the pause had
  refused as a failure, ending the run with `BLOCKED_REPEAT_FAILED`.
- Pause now holds the running repeat first; Resume releases the runtime, then continues the
  repeat. Only repeats held by the Pause button are resumed — a repeat paused from its own
  panel stays paused.
- A move cut off by the pause is not a failure: Resume sends the same move again.
- Resuming a multi-run also releases the runtime pause.
- No red "No multi-run in progress" message when only a single run is paused.
- Software validation only; not yet re-run on the physical arm.

# 0.4.1 — Emergency stop no longer blames robots on standby (2026-10-05)

- A robot whose runtime is not running (connection refused) is logged as skipped, not as
  "did not respond". A runtime that is up but times out or refuses is still reported.

# 0.4.0 — OMX J13 current limit, recovery result validation (2026-10-05)

Safety behaviour changed, so the minor version goes up.

- **OMX J13 current limit raised from 210/240 to 280/340** (sustained/instant, raw units).
  The "standing" pose (J12/J13 ≈ 1910, forearm level) puts the largest gravity load on J13.
  On the way back into it, J13 read 217 and 220 three samples in a row and a normal sequence
  was stopped twice. 280 ≈ 0.75 A and 340 ≈ 0.91 A are still less than half the fault value
  we have seen (802). **Not yet re-run on the physical arm at the new limit.**
- Each move result now reports the peak current per joint (`peak_currents`), so the next
  adjustment can come from measurements.
- Emergency-stop warnings name robots by display name instead of internal ID.

### Recovery result validation (prepared 2026-09-25)

- Verify remaining motor faults, complete position reads and hold results before
  reporting recovery success; keep movement blocked on failure.
- Confirmed full reset invokes hardware recovery after startup while preserving
  emergency stop and away mode. Normal start/ensure never invokes motor recovery.
- Report process startup and robot readiness separately, including unexpected
  simulation fallback and missing recovery responses.
- Describe motor reboot and torque release in the restart confirmation dialog.
- Add regression coverage for recovery failures and stop requests during recovery.
- Software and mock-device validation only; supervised physical recovery testing
  is still pending. See [recovery behaviour](docs/RECOVERY_RESET_BEHAVIOR.md).

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
