"""Four-joint ros2_control virtual arm. No hardware or vendor SDK is loaded."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    names = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_joint"]
    links, controls = ['<link name="base"/>'], []
    parent = "base"
    for index, name in enumerate(names):
        child = f"link_{index}"
        links.append(f'''<link name="{child}"/>
          <joint name="{name}" type="revolute">
            <parent link="{parent}"/><child link="{child}"/>
            <origin xyz="0 0 0.1"/><axis xyz="0 0 1"/>
            <limit lower="-1.57" upper="1.57" effort="10" velocity="1"/>
          </joint>''')
        controls.append(f'''<joint name="{name}">
          <command_interface name="position"/>
          <state_interface name="position"><param name="initial_value">0.0</param></state_interface>
          <state_interface name="velocity"/>
        </joint>''')
        parent = child
    urdf = '<robot name="hangeul_mock_arm">' + ''.join(links) + '''
      <ros2_control name="VirtualArm" type="system">
        <hardware><plugin>mock_components/GenericSystem</plugin>
          <param name="calculate_dynamics">true</param>
        </hardware>''' + ''.join(controls) + '</ros2_control></robot>'
    params = {"update_rate": 100,
              "joint_state_broadcaster.type": "joint_state_broadcaster/JointStateBroadcaster",
              "joint_trajectory_controller.type": "joint_trajectory_controller/JointTrajectoryController",
              "joint_trajectory_controller.joints": names,
              "joint_trajectory_controller.command_interfaces": ["position"],
              "joint_trajectory_controller.state_interfaces": ["position", "velocity"]}
    # Controller parameters are supplied via a launch-generated YAML file to the spawner.
    import tempfile
    import yaml
    from pathlib import Path
    folder = Path(tempfile.mkdtemp(prefix="hangeul_ros2_controllers_"))
    config = folder / "controllers.yaml"
    config.write_text(yaml.safe_dump({
        "controller_manager": {"ros__parameters": params},
        "joint_trajectory_controller": {"ros__parameters": {
            "joints": list(names), "command_interfaces": ["position"],
            "state_interfaces": ["position", "velocity"],
            "allow_partial_joints_goal": False,
            "constraints": {"goal_time": 2.0},
        }}}))
    return LaunchDescription([
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": urdf}], output="screen"),
        Node(package="controller_manager", executable="ros2_control_node",
             parameters=[str(config)], output="screen"),
        Node(package="controller_manager", executable="spawner",
             arguments=["joint_state_broadcaster", "joint_trajectory_controller",
                        "--param-file", str(config), "--controller-manager-timeout", "30"],
             output="screen"),
    ])
