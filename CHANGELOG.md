# Unreleased

- Add a ROS 2 arm adapter (`arm_ros2`, ros2_control JointTrajectoryController) with a bounded
  transport: fresh joint states, action feedback/result/cancel, and stale-state refusal.
- Add ROS 2 connection and one-axis Gazebo actuator physics verification tools, a torque-limit
  plugin, and the recorded evidence.
- **Verified in simulation only. Not yet tested on physical actuators.**

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
