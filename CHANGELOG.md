# 0.5.3 — Rest in Work/Rest mode ends on time even when the window is hidden (2026-11-10)

- Rest was counted as 600 one-second browser timers. With the window hidden (e.g. switched to another
  Windows virtual desktop) the browser ran those chained timers about once a minute, so a 10-minute rest
  could last hours and work never resumed. Rest now ends by its end time, and is checked again the moment
  the page becomes visible.
- Pausing during rest cleared the rest timer and handed nothing to Resume, so Resume never restarted the
  run. Pause now keeps the rest time left and Resume continues from it.
- Checked in a browser with throttled timers, hidden→visible and pause during rest; robot calls were
  faked in the test.
- Not yet: the Work/Rest schedule still runs inside the browser page. Closing the page, or the browser
  freezing it, stops the schedule. A pose's wait time (`delay_sec`) likely has the same pause problem
  (not fixed or tested).

# 0.5.2 — FR5 rviz window and Start-menu shortcut; WSL-only made explicit (2026-11-09)

- The simulator now opens a hangeul rviz screen (`install/ros2/fairino5.rviz`): fixed window size,
  MoveIt's goal-state arm (orange) hidden, the real arm (grey) drawn solid. The orange arm looked like
  a second robot; hangeul does not plan with MoveIt. The window *position* is not fixed — WSLg ignores
  it (tested).
- Windows Start-menu shortcut "FR5 rviz (hangeul)" to reopen the view after closing it:
  `sudo ./install/ros2/install_fr5_rviz_shortcut.sh` writes it for wherever this repository lives.
- Docs: FR5 runs on WSL/Linux only. A native Windows install (`Setup.bat` · `Start.bat`) does not
  start it and says why; the README had listed `run_wsl.bat` without saying so.
- `install/windows/run_wsl.bat`: Korean comment lines were misread by cmd and their fragments run as
  commands ("'은' is not recognized"). Comments are ASCII now; what the file does is unchanged.
- No robot behaviour changed.

# 0.5.1 — The robot list says what happened in words (2026-11-08)

- The robot list showed the raw verdict code (`Last: ACTUAL_MOTION_EXECUTED_ONCE`). Words for
  31 verdicts now live in `terms.py` (Korean · English) and the console sends them next to the code
  (`last_result_i18n`). An unknown code is never shown as is ("Blocked" / "Unknown result").
- A test collects the verdict codes from the runtime and console sources, so a new code without a
  word fails the suite.
- The narrow status column clipped the line on both sides and broke Korean words in the middle.
- Screen-text change only; no robot behaviour changed.

# 0.5.0 — FAIRINO FR5 in ROS 2 simulation (2026-11-08)

- **Not yet:** simulation only (ros2_control mock). The real FR5, the real controller
  (`fairino_hardware`) and its IP connection have not been tried. Joint ranges are 5° inside the
  URDF values, not measured. No hand. Not started on native Windows (WSL/Linux only).
- New part descriptor `arm_fairino5` (j1–j6, `/fairino5_controller`, port 8606, 0.5 rad/s) and
  safety limits `data/safety_limits_arm_fairino5.json`.
- **Safety behaviour change — releasing an emergency stop on a ROS 2 arm always failed.** The
  controller fills `error_string` ("Goal successfully reached!") even on success; it was reported as
  an error, so recovery verification read success as failure and each attempt also latched a
  disconnect. It is now an error only when the goal failed. OMX/MyCobot paths are unchanged.
- The runtime no longer turns a move on a named joint (`j1`) into HTTP 500 (`int(joint)`); unknown
  joints are refused with a reason.
- `install/run_runtime.sh` appends to PYTHONPATH instead of replacing it. Replacing it hid `rclpy`
  even after sourcing ROS 2, so the runtime came up in simulate mode.
- Launcher: an arm whose descriptor has a `ros2` section looks for its ROS 2 controller instead of a
  USB device. If none answers and the descriptor names a simulator, it starts that first; stop ends
  only simulators it started. `ros2 action list` is not used — the ros2 daemon kept reporting a
  stopped simulator's action as present.
- Screen: named joints were dropped by `parseInt` and **the OMX joints were drawn instead**. Arms in
  millidegrees are shown in degrees. Screens with numbered joints are unchanged (OMX screen HTML
  compared identical).
- **Safety behaviour change — micro-move default on the screen.** A freshly opened screen kept the
  OMX default (50 ticks), which degree-unit arms (MyCobot, FR5) read as 50°. It is now reset to the
  robot's default (5°). OMX is unchanged.
- Checked against `/joint_states` in the simulator: out-of-range refusal, move, stop/release, saving
  poses and running a sequence from the screen — `docs/FAIRINO_FR5_SIMULATION_20261108.md`.

# 0.4.4 — The screen shows a leftover emergency stop on open (2026-10-20)

- The runtime keeps an emergency-stop latch across restarts (by design), but the screen always
  started as "not stopped". Opened with a latch still set, runs were blocked while the button
  only offered "Emergency Stop" — you had to press stop again and then reset before anything moved.
- The console now reports runtime latches at `/api/estop-status`; the screen checks it on open and
  every 3 seconds, switches the button to Reset and logs which robot is stopped and why.
- It only syncs toward "stopped". An unreachable runtime is never shown as released; releasing
  still needs the operator's Reset.
- Software validation only; not yet re-run on the physical arm.

# 0.4.3 — Pause no longer trips a false disconnect (2026-10-19)

- Pausing during a move could latch the robot as disconnected with
  `comm=-1000` (Dynamixel `COMM_PORT_BUSY`). The stop path wrote to the serial port
  without the lock while the running move was still polling the same port.
  Now the stop asks the running move to step aside (it ends as `CANCELED`, which
  Resume re-sends), takes the serial port and holds the arm in place. A stop still
  never waits more than 1 second: if the port is not released, it holds without the lock.
- Pause and Resume no longer report standby robots (no runtime running) as
  "did not respond", the same rule as emergency stop in 0.4.1. Warnings use display names.
- Confirmed on the physical OMX by the operator.

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
