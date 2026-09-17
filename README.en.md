# Hangeul Robot Public Edition

Hangeul Robot is a lightweight physical-AI runtime and robot operation console.
It models robots as replaceable parts, computes available capabilities from the current configuration,
and gates execution through safety and verification checks.

This public edition includes both **simulation and direct connection paths for supported hardware**.
It includes OpenManipulator-X and MyCobot 280 M5 adapters, so users can move real robots after
verifying ports, limits, and stop behavior on their own hardware.
It does not include customer-specific integrations or commercial operation tools.

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
| Basic safety/current/temperature limit files | Included |
| Customer or commercial integrations | Excluded |

## Run

On Ubuntu/WSL, install Python 3, pip and the `python3-venv` package first.
The installer creates a project-local `.venv`, including test dependencies.
Hardware packages are optional for simulation; installation failures are reported.


```bash
./install/install.sh
./run.sh
```

Open:

```text
http://127.0.0.1:8099
```

Optional simulated runtime:

```bash
./install/run_runtime.sh arm_sim --simulate
```

Run the runtime in a second terminal. In the console, add a robot with `core_a`,
`arm_sim` and `hand_sim` to read positions and test jog, absolute and gripper moves.
The demo joint range is 0–4095 ticks. `--simulate` never opens physical hardware,
even when a physical arm descriptor is selected.

`run.sh` starts only the console. Physical control also requires a runtime.
The demo and OMX both default to port 8601; do not run both on that port.

Physical runtime examples:

```bash
./install/run_runtime.sh arm_omx
./install/run_runtime.sh arm_mycobot
```

Override the device port when needed:

```bash
DEVICE=/dev/ttyUSB1 ./install/run_runtime.sh arm_omx
DEVICE=/dev/ttyACM1 ./install/run_runtime.sh arm_mycobot
```

## Test

```bash
.venv/bin/python -m pytest -q
```

Verified in this prepared public folder:

```text
110 passed, 18 skipped
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
