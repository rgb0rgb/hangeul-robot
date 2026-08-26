"""자산 백업·복원 — 되돌릴 수 있는 상태의 근거."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import asset_backup


def _make(tmp_path):
    src = tmp_path / "src"
    (src / "robot_a").mkdir(parents=True)
    (src / "robot_a" / "poses.json").write_text(
        json.dumps({"poses": {"home": {"targets": {"11": 2048}}}}, ensure_ascii=False),
        encoding="utf-8")
    (src / "robot_a" / "state.json").write_text('{"run":"idle"}', encoding="utf-8")
    return src


def test_round_trip_preserves_content(tmp_path):
    src = _make(tmp_path)
    bundle = asset_backup.export(src)
    result = asset_backup.restore(bundle, tmp_path / "out")
    assert result["restored"] == 1
    assert asset_backup.verify(bundle, tmp_path / "out")["ok"] is True


def test_runtime_files_are_not_backed_up(tmp_path):
    bundle = asset_backup.export(_make(tmp_path))
    assert "state.json" not in bundle["instances"]["robot_a"]


def test_export_does_not_touch_the_source(tmp_path):
    src = _make(tmp_path)
    before = (src / "robot_a" / "poses.json").read_bytes()
    asset_backup.export(src)
    assert (src / "robot_a" / "poses.json").read_bytes() == before


def test_restore_refuses_to_overwrite(tmp_path):
    bundle = asset_backup.export(_make(tmp_path))
    asset_backup.restore(bundle, tmp_path / "out")
    try:
        asset_backup.restore(bundle, tmp_path / "out")
    except SystemExit as exc:
        assert "빈 디렉터리" in str(exc)
    else:
        raise AssertionError("덮어쓰기를 막지 않았다")


def test_corrupted_restore_is_detected(tmp_path):
    bundle = asset_backup.export(_make(tmp_path))
    asset_backup.restore(bundle, tmp_path / "out")
    (tmp_path / "out" / "robot_a" / "poses.json").write_text('{"poses":{}}', encoding="utf-8")
    check = asset_backup.verify(bundle, tmp_path / "out")
    assert check["ok"] is False and check["mismatches"]
