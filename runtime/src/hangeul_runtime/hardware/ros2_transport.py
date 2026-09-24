"""ROS 2 transport with independent executor, fresh state, and bounded actions.

Imported only when a ROS adapter is opened. No physical driver is started here.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from typing import Any


class Ros2Transport:
    def __init__(self, controller: str, joints: list[str], options: dict[str, Any]):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.action import ActionClient
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import JointState
        from control_msgs.action import FollowJointTrajectory

        self.joints = joints
        self.state_timeout = float(options.get("state_timeout_s", 2.0))
        self.connect_timeout = float(options.get("connect_timeout_s", 5.0))
        self.goal_margin = float(options.get("goal_timeout_margin_s", 3.0))
        if any(not math.isfinite(t) or t <= 0 for t in
               (self.state_timeout, self.connect_timeout, self.goal_margin)):
            raise ValueError("ROS timeouts must be finite and positive")
        self._state_lock = threading.Lock()
        self._goal_lock = threading.Lock()
        self._values: dict[str, tuple[float, float]] = {}
        self._active = None
        self._generation = 0
        self._inhibited = False
        self.feedback_count = 0
        self.context = Context()
        rclpy.init(context=self.context)
        self.node = Node("hangeul_arm_" + uuid.uuid4().hex[:10], context=self.context)
        self.client = ActionClient(self.node, FollowJointTrajectory,
                                   controller.rstrip("/") + "/follow_joint_trajectory")
        self.subscription = self.node.create_subscription(
            JointState, options.get("joint_states_topic", "/joint_states"),
            self._on_state, qos_profile_sensor_data)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()
        try:
            if not self.client.wait_for_server(timeout_sec=self.connect_timeout):
                raise TimeoutError("ROS trajectory action server is unavailable")
            deadline = time.monotonic() + self.connect_timeout
            while True:
                try:
                    self.joint_positions()
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("No complete, fresh ROS joint state")
                    time.sleep(0.02)
        except Exception:
            self.close()
            raise

    def _on_state(self, msg):
        now = time.monotonic()
        with self._state_lock:
            for name, value in zip(msg.name, msg.position):
                if name in self.joints and math.isfinite(value):
                    self._values[name] = (float(value), now)

    def joint_positions(self):
        now = time.monotonic()
        with self._state_lock:
            missing = [j for j in self.joints if j not in self._values or
                       now - self._values[j][1] > self.state_timeout]
            if missing:
                raise RuntimeError("Missing or stale ROS joint state: " + ", ".join(missing))
            return {j: self._values[j][0] for j in self.joints}

    def server_ready(self):
        return self.client.server_is_ready()

    @staticmethod
    def _wait(future, timeout):
        done = threading.Event()
        future.add_done_callback(lambda _: done.set())
        if not done.wait(timeout):
            raise TimeoutError("ROS action response timed out")
        return future.result()

    def _feedback(self, msg):
        with self._state_lock:
            self.feedback_count += 1

    def send_trajectory(self, *, joint_names, positions, time_from_start_s, label):
        from control_msgs.action import FollowJointTrajectory
        from trajectory_msgs.msg import JointTrajectoryPoint
        from builtin_interfaces.msg import Duration
        from action_msgs.msg import GoalStatus

        if not self.server_ready():
            return {"accepted": False, "result_ok": False, "error": "ROS server unavailable"}
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(joint_names)
        point = JointTrajectoryPoint()
        point.positions = list(positions)
        ns = max(1, round(time_from_start_s * 1_000_000_000))
        point.time_from_start = Duration(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)
        goal.trajectory.points = [point]
        with self._goal_lock:
            if self._inhibited:
                return {"accepted": False, "result_ok": False, "canceled": True,
                        "error": "ROS transport stopped; explicit recovery required"}
            generation = self._generation
            future = self.client.send_goal_async(goal, feedback_callback=self._feedback)

        # A cancel or timeout before goal acknowledgement must also cancel a late goal.
        def accepted_callback(f):
            try:
                handle = f.result()
            except Exception:
                return  # The waiting caller receives the transport exception.
            if handle is None or not handle.accepted:
                return
            with self._goal_lock:
                if generation != self._generation:
                    handle.cancel_goal_async()
                else:
                    self._active = handle
        future.add_done_callback(accepted_callback)
        handle = None
        result_future = None
        try:
            handle = self._wait(future, self.connect_timeout)
            if handle is None or not handle.accepted:
                return {"accepted": False, "result_ok": False, "error": "ROS goal rejected"}
            with self._goal_lock:
                if generation != self._generation:
                    handle.cancel_goal_async()
                else:
                    self._active = handle
            result_future = handle.get_result_async()
            def finished(_):
                with self._goal_lock:
                    if self._active is handle:
                        self._active = None
            result_future.add_done_callback(finished)
            response = self._wait(result_future, time_from_start_s + self.goal_margin)
            result = response.result
            return {"accepted": True,
                    "result_ok": response.status == GoalStatus.STATUS_SUCCEEDED and result.error_code == 0,
                    "canceled": response.status == GoalStatus.STATUS_CANCELED,
                    "status": response.status, "error_code": result.error_code,
                    "error": result.error_string, "feedback_count": self.feedback_count}
        except TimeoutError as exc:
            with self._goal_lock:
                self._generation += 1
                self._inhibited = True
                if handle is not None and handle.accepted:
                    handle.cancel_goal_async()
            return {"accepted": bool(handle and handle.accepted), "result_ok": False,
                    "timed_out": True, "error": str(exc)}
        finally:
            with self._goal_lock:
                if self._active is handle and (result_future is None or result_future.done()):
                    self._active = None

    def cancel_all(self):
        with self._goal_lock:
            self._generation += 1
            self._inhibited = True
            handle = self._active
        if handle is not None:
            answer = self._wait(handle.cancel_goal_async(), self.connect_timeout)
            return bool(answer.goals_canceling)
        return True

    def resume(self):
        # Called only by explicit runtime recovery, not automatically after an action.
        self.joint_positions()
        if not self.server_ready():
            raise RuntimeError("ROS action server is unavailable")
        with self._goal_lock:
            if self._active is not None:
                raise RuntimeError("Previous ROS action has not finished canceling")
            self._inhibited = False

    def close(self):
        try:
            self.cancel_all()
        except Exception as exc:
            # A vanished server cannot acknowledge cancellation. Still release local
            # DDS resources; this is not evidence that a physical actuator stopped.
            self.node.get_logger().warning(f"ROS close could not confirm cancellation: {exc}")
        finally:
            self.executor.shutdown(timeout_sec=3)
            self.thread.join(timeout=3)
            self.node.destroy_node()
            self.context.try_shutdown()
