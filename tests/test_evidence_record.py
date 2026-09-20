"""증거 기록 — 코드·가상·실물을 제품 안에서 구분한다 (2026-09-20).

문서에서만 구분하면 시간이 지나 섞인다. "검증됨"이 무엇으로 검증됐는지
제품이 들고 있어야 한다. 그리고 **통신 응답과 사람의 눈은 다른 증거다.**
"""
from __future__ import annotations

import pytest

from hangeul_console.evidence import EvidenceError, EvidenceLog


def _log():
    return EvidenceLog()


def test_a_record_keeps_what_kind_of_evidence_it_was():
    log = _log()
    ref = log.record(kind="hardware", method="measurement", subject="hand.close",
                     operator="운영자", outcome="통과")
    assert log.get(ref)["kind"] == "hardware"
    assert "실물" in log.describe(ref)


def test_code_evidence_is_not_dressed_up_as_hardware():
    log = _log()
    ref = log.record(kind="code", method="automated_test", subject="속도 불변식",
                     operator="시험", outcome="통과",
                     not_covered="실물 속도 계측")
    line = log.describe(ref)
    assert "코드" in line and "실물" not in line.split("—")[0]
    assert "확인하지 않음: 실물 속도 계측" in line


def test_communication_and_the_human_eye_are_different_evidence():
    """응답이 왔다는 것과 사람이 보고 붙어 있다고 한 것은 다르다."""
    log = _log()
    by_wire = log.record(kind="hardware", method="communication_response",
                         subject="hand", operator="런타임", outcome="응답 있음")
    by_eye = log.record(kind="hardware", method="operator_inspection",
                        subject="hand", operator="운영자", outcome="장착 확인")
    assert log.get(by_wire)["method"] != log.get(by_eye)["method"]
    assert "통신 응답" in log.describe(by_wire)
    assert "운영자 점검" in log.describe(by_eye)


def test_an_unknown_kind_is_refused():
    with pytest.raises(EvidenceError):
        _log().record(kind="대충", method="automated_test", subject="x",
                      operator="o", outcome="통과")


def test_an_unknown_method_is_refused():
    with pytest.raises(EvidenceError):
        _log().record(kind="code", method="느낌", subject="x",
                      operator="o", outcome="통과")


def test_an_incomplete_record_is_refused():
    with pytest.raises(EvidenceError):
        _log().record(kind="code", method="automated_test", subject="",
                      operator="o", outcome="통과")


def test_the_record_pins_what_configuration_it_was_about():
    """무엇에 대한 확인인지 없으면, 부품이 바뀐 뒤에도 그 증거가 살아남는다."""
    log = _log()
    ref = log.record(kind="hardware", method="measurement", subject="motion.move_pose",
                     operator="운영자", outcome="통과",
                     configuration_fingerprint="v2:sha256:abc",
                     meaning_digest="sha256:def")
    row = log.get(ref)
    assert row["configuration_fingerprint"] == "v2:sha256:abc"
    assert row["meaning_digest"] == "sha256:def"


def test_records_are_kept_not_replaced():
    """감사용이므로 지우지 않는다."""
    log = _log()
    first = log.record(kind="code", method="automated_test", subject="a",
                       operator="o", outcome="통과")
    second = log.record(kind="hardware", method="measurement", subject="a",
                        operator="o", outcome="통과")
    assert first != second
    assert log.get(first) and log.get(second)
