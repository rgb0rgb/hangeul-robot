"""눈(카메라) 부품 계약 — 팔 어댑터와 같은 자리에 둔다.

런타임은 카메라 종류를 모른다. 기술서가 `runtime_adapter`로 자기 어댑터를
밝히고, 런타임은 여기 적힌 것만 부른다.

팔에서 이 자리를 한 번 틀렸다(F1, xArm 반증 시험 20260817 — 런타임이 부품 이름을
문자열로 훑고 있었다). 눈은 처음부터 같은 모양으로 둔다. 웹캠이든 CSI든 IP
카메라든, 어댑터 한 장과 기술서 한 줄로 붙어야 한다.

**이 계약에는 추적이 없다.** 눈은 프레임을 줄 뿐이고, 그걸로 무엇을 하는지는
vision/ 쪽 일이다. 눈을 바꿔도 추적기는 그대로여야 하기 때문이다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CameraAdapter(ABC):
    """눈 부품 하나. 프레임을 주는 것까지가 책임이다."""

    module_class = "eye"

    @abstractmethod
    def __enter__(self) -> "CameraAdapter":
        """카메라를 연다. 열리지 않으면 예외를 올린다 — 조용히 검은 화면을 주지 않는다."""

    @abstractmethod
    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """카메라를 놓는다."""

    @abstractmethod
    def read_frame(self) -> Any:
        """지금 프레임 하나. 못 읽으면 None을 돌려준다(예외가 아니다 — 한 장쯤은 빌 수 있다)."""

    @property
    @abstractmethod
    def frame_size(self) -> tuple[int, int]:
        """(가로, 세로). 기술서의 limits를 실제로 따랐는지 여기서 확인할 수 있어야 한다."""

    def describe(self) -> dict[str, Any]:
        """지금 이 눈이 무엇인지. 화면이 '있는 척'을 못 하게 하려고 둔다."""
        width, height = self.frame_size
        return {"module_class": self.module_class, "width": width, "height": height}
