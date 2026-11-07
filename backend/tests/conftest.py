"""Test setup: a throwaway SQLite DB and fake models (no network, no API keys used)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="cqa-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JEV_ENABLED"] = "true"
os.environ["TYPESAFE_API_KEY"] = "test"
os.environ["GOOGLE_API_KEY"] = "test"
os.environ["SEED_DATASET"] = ""  # keep the test DB small; seeding is tested explicitly
os.environ["AUDIO_DIR"] = f"{_tmp}/audio"  # uploaded recordings go to the temp dir, not the repo

import pytest  # noqa: E402

from app.checklist import DEFAULT_CHECKLIST, ChecklistIn  # noqa: E402
from app.llm import gemini, jev  # noqa: E402

CRIT = ChecklistIn(**DEFAULT_CHECKLIST).criteria

TRANSCRIPT = [
    {"timestamp": "00:00", "speaker": "client", "text": "Где посмотреть тариф?"},
    {"timestamp": "00:02", "speaker": "bot", "text": "Здравствуйте! Я AIM."},
    {"timestamp": "00:05", "speaker": "system", "text": "Эскалация на оператора."},
    {"timestamp": "00:40", "speaker": "operator", "text": "Здравствуйте, меня зовут Алина. Откройте «Кабинет»."},
    {"timestamp": "01:00", "speaker": "client", "text": "Нашла, спасибо."},
    {"timestamp": "01:10", "speaker": "operator", "text": "Если появятся вопросы — пишите. До свидания!"},
]

GOOD = {"c01_contact": "yes", "c02_needs": "na", "c03_identification": "na", "c04_consultation": "20",
        "c05_empathy": "yes", "c06_management": "10", "c07_closing": "yes", "c08_gross": "no"}


class FakeModels:
    """Configurable stand-ins for Gemini and Jev. Answers are per criterion key."""

    def __init__(self):
        self.gemini_answers = dict(GOOD)
        self.jev_answers = dict(GOOD)
        self.jev_prob = 0.95
        self.adjudicate_to = {}  # key -> answer returned by the re-check
        self.evidence = {k: [3] for k in GOOD}
        self.calls = {"gemini": 0, "adjudication": 0, "jev": 0, "mood": 0}
        self.jev_fail = False
        self.mood_fail = False
        self.coaching_fail = False
        self.operator = "Алина"

    def _crit_block(self, keys, answers):
        return {k: {"analysis": "a", "answer": answers[k], "explanation": f"{k} — {answers[k]} [3]",
                    "evidence": self.evidence.get(k, [3]), "checked_range": [3, 5], "confidence": "high"}
                for k in keys}

    async def generate_json(self, prompt, schema, system=None, retries=2, validate=None, contents=None):
        props = schema["properties"]
        usage = {"input_tokens": 1000, "output_tokens": 200, "thinking_tokens": 100, "calls": 1}
        if "facts" in props:  # main evaluation call
            self.calls["gemini"] += 1
            keys = list(props["criteria"]["properties"])
            data = {"facts": {"operator_name": self.operator, "client_language": "RU", "client_request": "тариф",
                              "request_formulated": True, "request_type": "general_info",
                              "identity_required": False, "identity_verified_turn": None,
                              "operator_first_turn": 3, "client_dissatisfied": False, "explicit_wait": False,
                              "ending": "operator_farewell"},
                    "criteria": self._crit_block(keys, self.gemini_answers)}
            if "feedback" in props:
                data["feedback"] = {"summary": "ok", "strengths": [{"text": "s", "turn": 3}],
                                    "improvements": [{"text": "i", "turn": 5, "criterion_key": "c07_closing",
                                                      "example_phrase": None}]}
        elif "turns" in props:  # speech-to-text of an uploaded recording
            data = {"language": "RU", "turns": [
                {"start": "0:03", "speaker": "operator", "text": "Фридом брокер, здравствуйте, меня зовут [Имя скрыто]."},
                {"start": "00:09", "speaker": "client", "text": "Где  посмотреть тариф?"},
                {"start": "1:02", "speaker": "operator", "text": "В разделе «Профиль». До свидания!"}]}
        elif "trajectory" in props:  # client mood
            self.calls["mood"] += 1
            if self.mood_fail:
                raise RuntimeError("mood down")
            data = {"start": "anxious", "end": "positive", "trajectory": "improved", "confidence": "high",
                    "summary": "Волновался, в конце поблагодарил [4].",
                    "moments": [{"turn": 0, "mood": "anxious", "note": "n"}, {"turn": 99, "mood": "calm", "note": "x"}]}
        elif "weekly_plan" in props:  # operator coaching
            self.calls["coaching"] = self.calls.get("coaching", 0) + 1
            if self.coaching_fail:
                raise RuntimeError("coaching down")
            import re
            keys = re.findall(r"^### (\S+) —", prompt, re.M)
            data = {"summary": "Хорошо отвечаете, поработайте над завершением.",
                    "focus": [{"criterion_key": k, "tip": f"tip {k}", "practice_phrase": "Хорошего дня!"} for k in keys],
                    "weekly_plan": ["a", "b", "c"]}
        elif "appeal_justified" in props:  # appeal AI review
            data = {"analysis": "a", "answer": "no", "explanation": "review", "evidence": [5],
                    "checked_range": None, "confidence": "medium", "appeal_justified": True}
        else:  # adjudication of disputed criteria
            self.calls["adjudication"] += 1
            keys = list(props)
            data = self._crit_block(keys, {k: self.adjudicate_to.get(k, self.gemini_answers[k]) for k in keys})
        if validate:
            validate(data)
        return data, usage

    async def jev_ask(self, state, questions, retries=2):
        self.calls["jev"] += 1
        if self.jev_fail:
            raise RuntimeError("jev down")
        answers = {k: {"type": "choice", "choice": self.jev_answers[k], "confidence": self.jev_prob,
                       "probabilities": {self.jev_answers[k]: self.jev_prob}} for k in questions}
        return answers, {"input_tokens": 5000, "output_tokens": 50, "model": "jev-fake"}


@pytest.fixture
def fake(monkeypatch):
    f = FakeModels()
    monkeypatch.setattr(gemini, "generate_json", f.generate_json)
    monkeypatch.setattr(jev, "ask", f.jev_ask)
    monkeypatch.setattr(jev, "enabled", lambda: True)
    return f


@pytest.fixture
def conv():
    return {"id": "t-1", "channel": "agent chat", "language": "RU", "transcript": TRANSCRIPT}
