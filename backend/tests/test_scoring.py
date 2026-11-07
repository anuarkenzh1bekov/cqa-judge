import pytest

from app.checklist import DEFAULT_CHECKLIST, ChecklistIn, Criterion
from app.scoring import compute, normalize_answer, round2, validate_answer

CRIT = ChecklistIn(**DEFAULT_CHECKLIST).criteria
ALL_YES = {"c01_contact": "yes", "c02_needs": "yes", "c03_identification": "yes", "c04_consultation": "20",
           "c05_empathy": "yes", "c06_management": "10", "c07_closing": "yes", "c08_gross": "no"}


def test_default_weights_sum_to_100():
    assert sum(c.weight for c in CRIT) == 100


def test_perfect_dialog():
    r = compute(CRIT, ALL_YES)
    assert r["total"] == 100.0 and r["gross_error"] is False


def test_scale_proportional():
    a = dict(ALL_YES, c04_consultation="15", c06_management="7")
    # 15/20*20 = 15, 7/10*15 = 10.5 -> 100 - 5 - 4.5 = 90.5
    assert compute(CRIT, a)["total"] == 90.5


def test_na_redistribution():
    a = dict(ALL_YES, c03_identification="na", c01_contact="no")
    # applicable weight 80, earned 70 -> 87.5
    r = compute(CRIT, a)
    assert r["total"] == 87.5
    assert r["criteria"]["c03_identification"]["applicable"] is False
    assert r["criteria"]["c02_needs"]["max_points"] == round2(15 / 80 * 100)
    assert sum(v["max_points"] or 0 for v in r["criteria"].values()) == pytest.approx(100, abs=0.05)


def test_rounding_two_decimals():
    a = dict(ALL_YES, c02_needs="na", c07_closing="na", c01_contact="no", c06_management="4")
    # applicable 80: 0 + 20 + 20 + 15 + 6 = 61 / 80 = 76.25
    assert compute(CRIT, a)["total"] == 76.25
    # applicable 65: 10 + 20 + 15 + 10.5 + 5 = 60.5 / 65 = 93.0769... -> 93.08
    a2 = dict(ALL_YES, c03_identification="na", c02_needs="na", c06_management="7")
    assert compute(CRIT, a2)["total"] == 93.08


def test_gross_error_flag_separate():
    r = compute(CRIT, dict(ALL_YES, c08_gross="yes"))
    assert r["total"] == 100.0 and r["gross_error"] is True


def test_no_applicable_criteria_total_none():
    crit = [Criterion(key="a", name="A", description="d", type="binary", weight=10, na_allowed=True, na_condition="x"),
            Criterion(key="g", name="G", description="d", type="flag", weight=0)]
    assert compute(crit, {"a": "na", "g": "no"})["total"] is None


def test_na_not_allowed_rejected():
    with pytest.raises(ValueError):
        validate_answer(CRIT[0], "na")


def test_answer_normalization():
    assert normalize_answer("Да") == "yes"
    assert normalize_answer("15.0") == "15"
    assert validate_answer(CRIT[3], 20) == "20"


def test_sections():
    r = compute(CRIT, dict(ALL_YES, c01_contact="no"))
    assert r["sections"]["Начало и понимание запроса"]["score_pct"] == 60.0
    assert "Грубые нарушения" not in r["sections"]


def test_flag_weight_must_be_zero():
    with pytest.raises(ValueError):
        Criterion(key="g", name="G", description="d", type="flag", weight=5)
