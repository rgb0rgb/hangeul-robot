"""Launch generated effort bench; BENCH_FOLDER must contain its model/config."""
import os
from pathlib import Path
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    folder = Path(os.environ["BENCH_FOLDER"])
    urdf = (folder / "bench.urdf").read_text()
    return LaunchDescription([
        ExecuteProcess(cmd=["gz", "sim", "-r", "-s", str(folder / "world.sdf")], output="screen"),
        Node(package="ros_gz_bridge", executable="parameter_bridge",
             arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"], output="screen"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": urdf}], output="screen"),
        Node(package="ros_gz_sim", executable="create",
             arguments=["-world", "actuator_bench", "-file", str(folder / "bench.urdf"), "-name", "bench"], output="screen"),
        Node(package="controller_manager", executable="spawner",
             arguments=["joint_state_broadcaster", "joint_trajectory_controller", "--controller-manager-timeout", "60"], output="screen"),
    ])
