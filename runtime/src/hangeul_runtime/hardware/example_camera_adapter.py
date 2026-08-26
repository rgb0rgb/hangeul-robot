from __future__ import annotations

from typing import Any

from hangeul_runtime.abstraction.camera_adapter import CameraAdapter


class ExampleCameraAdapter(CameraAdapter):
    """Public demo camera adapter. It exposes a frame contract without hardware."""

    def __init__(self, device: str = "", *, descriptor: dict[str, Any] | None = None):
        limits = (descriptor or {}).get("limits") or {}
        self._frame_size = (int(limits.get("width") or 640), int(limits.get("height") or 480))

    def __enter__(self) -> "ExampleCameraAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size

    def read_frame(self) -> Any:
        return None

