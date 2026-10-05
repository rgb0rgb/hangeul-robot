# Recovery and restart verification

Updated: 2026-09-25

An explicit **Full reset and restart** now restarts the programs, then requests
motor fault recovery and verifies a hold at the measured current position. Lower
or support the arm and supervise the procedure: motor reboot can release torque.
The confirmation dialog describes these hardware operations. The console restart
API requires `confirmed: true`; ordinary start and ensure operations do not invoke
motor recovery.

Emergency-stop and away-mode latches remain set across restart. If either is set,
the launcher reports `needs_operator` without attempting motor recovery. Use the
existing confirmed stop-release procedure after checking the robot. Previous
sequences and repeat jobs are not resumed automatically.

Recovery succeeds only after checking:

- Adapter fault-recovery results, including remaining errors, failed reboot
  acknowledgements and missing enabled servos.
- Positions for all enabled arm joints.
- A successful hold result; explicit failure, timeout, cancellation and missing
  result evidence are rejected.
- A hold for a gripper rebooted during recovery.
- A second position read after holding.

Recovery errors retain a movement-blocking latch. A new emergency stop during
recovery is not cleared by the finishing recovery request. Temperature checks
remain enabled for the recovery hold. There is no repeated reboot loop.

`data/run/last_report.json` distinguishes `processes_started` from `robots_ready`.
Each runtime has `ready` and `readiness` fields. An unexpected fallback from real
hardware to simulation is `disconnected`, not ready. Missing responses are
`unknown`, not successful. An intentionally configured simulator is labelled
`simulated`; its readiness is not physical-hardware evidence.

New runtime endpoint: `POST /api/recover-after-restart`, with an operator name and
`confirmed: true`. It retains operator safety latches. `/api/estop-reset` uses the
same verification but can release the existing emergency stop after success.

## Validation scope

Regression tests inject failed motor reboot, remaining fault registers, controller
errors, missing joints, failed/unknown hold results, a new stop during recovery,
and unexpected simulation fallback. They also check that normal start/ensure do
not reboot motors.

These are software tests using fake devices and temporary storage. Physical fault
recovery and the resulting arm/gripper behaviour still require supervised hardware
validation. A successful server start is not proof of physical recovery.

Persistent overheating, missing power, broken wiring and damaged hardware cannot
be repaired by restarting software. Their causes must be corrected before the
robot can become ready. See the [ROBOTIS XM430-W350 Shutdown documentation](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/#shutdown63).

```bash
python3 -m pytest -q tests/test_runtime_recovery.py tests/test_launcher.py
python3 -m pytest -q
python3 tools/publish_check.py
```
