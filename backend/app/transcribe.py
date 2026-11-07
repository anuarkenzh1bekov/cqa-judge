"""Speech-to-text for uploaded call recordings (Gemini audio input).

Produces a transcript in the same shape as the organizers' records, so the evaluation pipeline does not care
whether a conversation came from the dataset or from a recording. Personal data is masked like in the dataset.
"""
import time

from google.genai import types

from .config import settings
from .llm import gemini

# Formats Gemini accepts for audio input.
MIME = {".mp3": "audio/mp3", ".wav": "audio/wav", ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac",
        ".aiff": "audio/aiff", ".aif": "audio/aiff"}

PROMPT = """Транскрибируй запись звонка в службу поддержки брокера Freedom Broker.
- Дословно, на языке оригинала (русский, казахский, английский; смешанную речь оставляй как есть). Не пересказывай и не исправляй.
- Раздели речь на реплики и укажи, кто говорит:
  operator — сотрудник поддержки (обычно представляется: «Фридом брокер, здравствуйте, меня зовут …»);
  client — клиент;
  bot — автоответчик / голосовое меню («для выбора русского языка нажмите 2»).
- start — время начала реплики от начала записи в формате мм:сс.
- Персональные данные заменяй метками везде, где они звучат, в том числе когда собеседник повторяет или
  переспрашивает имя («Мирас?» → «[Имя скрыто]?»): имя и фамилия → [ФИО скрыто] (имя оператора → [Имя скрыто]),
  номер счёта, карты, телефона, ИИН, код из СМС → [номер скрыт], дата рождения → [дата скрыта].
- Неразборчивое — [неразборчиво]. Музыку ожидания, гудки и тишину пропускай.
- language — основной язык клиента: RU, KZ или EN."""

SCHEMA = {
    "type": "object", "required": ["language", "turns"],
    "properties": {
        "language": {"type": "string", "enum": ["RU", "KZ", "EN"]},
        "turns": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["start", "speaker", "text"],
            "properties": {"start": {"type": "string"},
                           "speaker": {"type": "string", "enum": ["operator", "client", "bot"]},
                           "text": {"type": "string"}}}},
    },
}


def _mmss(t: str) -> str:
    parts = [p for p in str(t).strip().split(":") if p != ""]
    try:
        nums = [int(float(p)) for p in parts]
    except ValueError:
        return "00:00"
    sec = 0
    for n in nums:
        sec = sec * 60 + n
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _validate(data):
    if not [t for t in data["turns"] if t["text"].strip()]:
        raise ValueError("empty transcript")


async def run(audio: bytes, mime: str) -> dict:
    """Returns {language, transcript, usage, cost_usd, duration_ms}."""
    t0 = time.perf_counter()
    data, usage = await gemini.generate_json(
        PROMPT, SCHEMA, validate=_validate,
        contents=[types.Part.from_bytes(data=audio, mime_type=mime), PROMPT])
    turns = [{"timestamp": _mmss(t["start"]), "speaker": t["speaker"], "text": " ".join(t["text"].split())}
             for t in data["turns"] if t["text"].strip()]
    transcript = [{"timestamp": "00:00", "speaker": "system",
                   "text": f"Транскрипт получен автоматически ({settings.gemini_model}) из загруженной записи."}] + turns
    return {"language": data["language"], "transcript": transcript, "usage": usage,
            "cost_usd": round(gemini.cost_usd(usage), 6), "duration_ms": int((time.perf_counter() - t0) * 1000)}
