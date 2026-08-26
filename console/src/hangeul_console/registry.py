"""로봇 등록 — 부품 목록으로 구성을 만든다.

로봇 하나 = 몸통에 어떤 부품을 꽂았는가. 그것뿐이다.
관절 번호도 단위도 여기 없다. 부품 기술서가 들고 있다.

    install/modules/*.json   부품 기술서
    install/robots/*.json    어떤 부품을 꽂았는가
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import configuration as cfg
from .module import Module, load_all

ROBOT_FORMAT = "hangeul_robot.robot.v1"


class RegistryError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


class Registry:
    def __init__(self, module_dir: Path, robot_dir: Path):
        self.module_dir = Path(module_dir)
        self.robot_dir = Path(robot_dir)
        self.modules: dict[str, Module] = {}
        self.configs: dict[str, cfg.Configuration] = {}
        self.problems: list[str] = []
        self._stamp: tuple = ()
        self.reload()

    def _files_stamp(self) -> tuple:
        """부품·구성 파일의 상태 도장. 부품을 바꿔 끼우면 이 값이 달라진다."""
        out = []
        for folder in (self.module_dir, self.robot_dir):
            if Path(folder).is_dir():
                for path in sorted(Path(folder).glob("*.json")):
                    out.append((str(path), path.stat().st_mtime_ns, path.stat().st_size))
        return tuple(out)

    def refresh(self) -> bool:
        """기술서가 바뀌었으면 다시 읽는다.

        부품 교체는 프로그램을 껐다 켜는 일이 아니다 — 기술서를 갈아 끼우면
        그 자리에서 다른 몸이 되어야 한다. 그래야 지문이 바뀌고, 옛 자세가
        실행 전에 막힌다.
        """
        stamp = self._files_stamp()
        if stamp == self._stamp:
            return False
        self.reload()
        return True

    def reload(self) -> None:
        self.configs, self.problems = {}, []
        self._stamp = self._files_stamp()
        self.modules, module_problems = load_all(self.module_dir)
        self.problems.extend(module_problems)
        if not self.robot_dir.is_dir():
            return

        used_runtime: dict[str, str] = {}
        for path in sorted(self.robot_dir.glob("*.json")):
            # 예시는 등록이 아니다. 복사해 쓰라고 둔 견본이므로 로봇으로 세지 않는다
            # (세면 견본의 런타임 주소가 진짜 로봇과 충돌한다).
            if path.name.endswith(".example.json"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self.problems.append(f"{path.name}: 읽을 수 없음 ({exc})")
                continue
            instance_id = data.get("instance_id")
            wanted = data.get("modules") or []
            if not instance_id or not wanted:
                self.problems.append(f"{path.name}: instance_id와 modules가 필요합니다")
                continue
            try:
                config = cfg.build(instance_id, data.get("display_name") or instance_id,
                                   self.modules, wanted)
            except cfg.ConfigurationError as exc:
                self.problems.append(f"{instance_id}: {exc}")
                continue
            config.runtime_url_value = data.get("runtime_url") or ""

            # 한 장치에 한 주인 — 그러나 **목록에서 빼는 방식으로 지키지 않는다.**
            # 같은 팔을 쓰는 로봇 두 대는 같은 런타임을 본다. 나중 것을 목록에서
            # 빼버리면 사람이 방금 만든 로봇이 흔적도 없이 사라진다(실제로 그랬다).
            # 동시에 쓰지 못하게 막는 것은 장치 임대(device_lease)가 실행 순간에 한다.
            owner = used_runtime.get(config.runtime_url_value)
            if owner and config.runtime_url_value:
                config.shares_runtime_with = owner
            used_runtime.setdefault(config.runtime_url_value, instance_id)

            self.problems.extend(f"{instance_id}: {p}" for p in config.problems)
            self.configs[instance_id] = config

    def get(self, instance_id: str) -> cfg.Configuration:
        try:
            return self.configs[instance_id]
        except KeyError:
            raise RegistryError("unknown_instance", f"등록되지 않은 로봇: {instance_id}") from None

    def all(self) -> list[cfg.Configuration]:
        return list(self.configs.values())
