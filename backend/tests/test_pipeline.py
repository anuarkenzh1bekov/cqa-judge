"""Merge logic between Gemini and Jev, evidence validation, scoring - with fake models."""
import asyncio

from app import pipeline
from tests.conftest import CRIT


def run(conv):
    return asyncio.run(pipeline.evaluate(conv, CRIT))


def by_key(out):
    return {r["key"]: r for r in out["results"]}


def test_all_agree(fake, conv):
    out = run(conv)
    r = by_key(out)
    assert all(x["agreement"] == "agree" for x in r.values())
    assert out["score"]["total"] == 100.0
    assert fake.calls == {"gemini": 1, "adjudication": 0, "jev": 1}
    assert not any(x["needs_review"] for x in r.values())
    assert r["c01_contact"]["evidence"][0]["speaker"] == "operator"  # evidence enriched from transcript


def test_confident_disagreement_triggers_adjudication(fake, conv):
    fake.jev_answers["c07_closing"] = "no"
    fake.adjudicate_to["c07_closing"] = "no"
    out = run(conv)
    r = by_key(out)["c07_closing"]
    assert r["agreement"] == "disputed" and r["adjudicated"]
    assert r["answer"] == "no" and r["adjudication"]["changed"] is True
    assert r["gemini"]["answer"] == "yes" and r["jev"]["answer"] == "no"
    assert fake.calls["adjudication"] == 1
    assert out["score"]["total"] < 100


def test_unconfident_disagreement_only_flags(fake, conv):
    fake.jev_answers["c05_empathy"] = "no"
    fake.jev_prob = 0.55
    out = run(conv)
    r = by_key(out)["c05_empathy"]
    assert r["agreement"] == "review" and r["answer"] == "yes"
    assert r["needs_review"] and "models_disagree" in r["review_reasons"]
    assert fake.calls["adjudication"] == 0


def test_adjacent_scale_steps_are_minor(fake, conv):
    fake.jev_answers["c04_consultation"] = "15"
    out = run(conv)
    r = by_key(out)["c04_consultation"]
    assert r["agreement"] == "minor" and r["answer"] == "20" and not r["needs_review"]


def test_jev_failure_falls_back_to_gemini(fake, conv):
    fake.jev_fail = True
    out = run(conv)
    assert all(x["agreement"] == "gemini_only" for x in out["results"])
    assert out["usage"]["jev_error"] == "jev down"
    assert out["score"]["total"] == 100.0


def test_invalid_evidence_is_dropped_and_flagged(fake, conv):
    fake.evidence["c01_contact"] = [3, 99, -1]
    r = by_key(run(conv))["c01_contact"]
    assert [e["index"] for e in r["evidence"]] == [3]
    assert "invalid_evidence_dropped" in r["review_reasons"]


def test_na_redistribution_in_pipeline(fake, conv):
    out = run(conv)
    # c02 and c03 are N/A -> applicable weight 65 -> c01 max points = 10/65*100
    assert by_key(out)["c01_contact"]["max_points"] == 15.38
    assert by_key(out)["c03_identification"]["applicable"] is False


def test_feedback_gets_timestamps(fake, conv):
    fb = run(conv)["feedback"]
    assert fb["improvements"][0]["timestamp"] == "01:10"


def test_prompt_is_built_from_checklist(conv):
    from app import prompts
    from app.checklist import Criterion
    extra = Criterion(key="x_name", name="Обращение по имени", description="Да — назвал клиента по имени",
                      type="binary", weight=5)
    p = prompts.build_eval_prompt(CRIT + [extra], conv)
    s = prompts.build_eval_schema(CRIT + [extra])
    assert "Обращение по имени" in p and "[3] (00:40) OPERATOR" in p
    assert s["properties"]["criteria"]["properties"]["x_name"]["properties"]["answer"]["enum"] == ["yes", "no"]
    assert "x_name" in prompts.jev_questions(CRIT + [extra])
