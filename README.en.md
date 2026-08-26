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
python3 -m pytest -q
```

Verified in this prepared public folder:

```text
79 passed, 16 skipped
```

## Safety Notice

This public edition can command supported physical robots when connected to hardware adapters.
The public edition is not a safety-certified industrial control system.
Always verify limits and stop behavior on your own hardware before enabling physical motion.

## License

Apache License 2.0
