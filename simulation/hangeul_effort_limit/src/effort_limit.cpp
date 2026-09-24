// Simulation only. A final output clamp, not an electrical or thermal motor model.
#include <algorithm>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include "gz_ros2_control/gz_system_interface.hpp"
#include "pluginlib/class_loader.hpp"
#include "pluginlib/class_list_macros.hpp"

namespace hangeul_sim {
class EffortLimitSystem : public gz_ros2_control::GazeboSimSystemInterface {
  using Base = gz_ros2_control::GazeboSimSystemInterface;
  using CallbackReturn = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;
  // Declaration order keeps the loader alive until the wrapped plugin is destroyed.
  pluginlib::ClassLoader<Base> loader_{"gz_ros2_control", "gz_ros2_control::GazeboSimSystemInterface"};
  std::shared_ptr<Base> plant_;
  std::vector<hardware_interface::CommandInterface> plant_commands_;
  std::vector<std::string> names_;
  std::vector<double> requested_, applied_, limits_;
public:
  CallbackReturn on_init(const hardware_interface::HardwareInfo & info) override {
    if (Base::on_init(info) != CallbackReturn::SUCCESS) return CallbackReturn::ERROR;
    for (const auto & joint : info.joints) {
      if (joint.command_interfaces.size() != 1 || joint.command_interfaces[0].name != "effort")
        throw std::invalid_argument("EffortLimitSystem requires effort-only joints");
      const auto & iface = joint.command_interfaces[0];
      const double cap = std::stod(iface.max);
      if (!std::isfinite(cap) || cap <= 0 || std::stod(iface.min) != -cap)
        throw std::invalid_argument("Finite symmetric effort limits required");
      names_.push_back(joint.name); limits_.push_back(cap);
    }
    requested_.resize(names_.size(), 0.0); applied_.resize(names_.size(), 0.0);
    return plant_->on_init(info);
  }
  bool initSim(rclcpp::Node::SharedPtr & node, std::map<std::string, sim::Entity> & joints,
               const hardware_interface::HardwareInfo & info, sim::EntityComponentManager & ecm,
               unsigned int rate) override {
    plant_ = loader_.createSharedInstance("gz_ros2_control/GazeboSimSystem");
    return plant_->initSim(node, joints, info, ecm, rate);
  }
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override {
    auto states = plant_->export_state_interfaces();
    for (size_t i = 0; i < names_.size(); ++i)
      states.emplace_back(names_[i], "applied_effort", &applied_[i]);
    return states;
  }
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override {
    plant_commands_ = plant_->export_command_interfaces();
    if (plant_commands_.size() != names_.size()) throw std::runtime_error("Unexpected command interfaces");
    std::vector<hardware_interface::CommandInterface> commands;
    for (size_t i = 0; i < names_.size(); ++i) {
      if (plant_commands_[i].get_name() != names_[i] + "/effort")
        throw std::runtime_error("Unexpected joint command order");
      commands.emplace_back(names_[i], "effort", &requested_[i]);
    }
    return commands;
  }
  CallbackReturn on_configure(const rclcpp_lifecycle::State & s) override { return plant_->on_configure(s); }
  CallbackReturn on_activate(const rclcpp_lifecycle::State & s) override { return plant_->on_activate(s); }
  CallbackReturn on_deactivate(const rclcpp_lifecycle::State & s) override { return plant_->on_deactivate(s); }
  hardware_interface::return_type perform_command_mode_switch(
      const std::vector<std::string> & start, const std::vector<std::string> & stop) override {
    return plant_->perform_command_mode_switch(start, stop);
  }
  hardware_interface::return_type read(const rclcpp::Time & t, const rclcpp::Duration & d) override {
    return plant_->read(t, d);
  }
  hardware_interface::return_type write(const rclcpp::Time & t, const rclcpp::Duration & d) override {
    bool invalid = false;
    for (size_t i = 0; i < requested_.size(); ++i) {
      invalid = invalid || !std::isfinite(requested_[i]);
      applied_[i] = std::isfinite(requested_[i]) ? std::clamp(requested_[i], -limits_[i], limits_[i]) : 0.0;
      if (!plant_commands_[i].set_value(applied_[i])) return hardware_interface::return_type::ERROR;
    }
    const auto result = plant_->write(t, d);
    return invalid ? hardware_interface::return_type::ERROR : result;
  }
};
}  // namespace hangeul_sim
PLUGINLIB_EXPORT_CLASS(hangeul_sim::EffortLimitSystem, gz_ros2_control::GazeboSimSystemInterface)
