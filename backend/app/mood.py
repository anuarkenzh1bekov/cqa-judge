"""Client mood: how the client felt at the start and at the end, and the moments where it changed.

Separate from the checklist evaluation: it never changes the score, and if it fails the evaluation still succeeds.
For calls with a recording the audio is sent too, so the tone of voice (raised voice, fast speech, long pauses)
is heard rather than guessed from the transcript. The model is told not to judge whether anyone is truthful:
voice cues do not show that, and a "lie detector" score would be unfair to clients and operators.
"""
import logging

from google.genai import types

from . import audio, prompts
from .config import settings
from .llm import gemini

log = logging.getLogger(__name__)

MOODS = ["calm", "positive", "confused", "anxious", "irritated", "angry"]
OPERATOR_TONES = ["friendly", "neutral", "tense", "irritated"]

_RULES = """Определи эмоциональное состояние КЛИЕНТА (не оператора и не бота) по ходу диалога.
Состояния: calm — спокоен; positive — доволен, благодарит; confused — не понимает, растерян;
anxious — волнуется, торопится, боится за деньги; irritated — раздражён, недоволен; angry — злится, требует, грубит.
- start — состояние в начале обращения, end — в последних репликах клиента.
- trajectory: improved — стало лучше, worsened — хуже, unchanged — без изменений.
- moments — до 4 реплик, где состояние видно лучше всего или меняется; turn — номер реплики [n] из транскрипта.
- summary — 1–2 предложения по-русски: что чувствовал клиент и почему (из-за чего изменилось).
- Не делай выводов о правдивости, честности или скрытых намерениях — по тексту и голосу это определить нельзя.
- Если клиент почти ничего не написал, ставь calm и confidence low."""

_AUDIO_RULES = """
К запросу приложена запись звонка. Оцени по ГОЛОСУ (темп, громкость, интонация, паузы, вздохи), а не только по словам:
- voice.client_tone и voice.operator_tone — преобладающий тон в записи;
- voice.moments — до 4 моментов: time «мм:сс» от начала записи, mood клиента, cue — что именно слышно
  («повышает голос», «говорит быстро», «долгая пауза перед ответом»);
- voice.summary — 1 предложение: совпадает ли тон голоса с тем, что видно по тексту.
Ошибки автоматической транскрибации не считай эмоциями."""


def _schema(with_voice: bool) -> dict:
    mood = {"type": "string", "enum": MOODS}
    props = {
        "start": mood, "end": mood,
        "trajectory": {"type": "string", "enum": ["improved", "unchanged", "worsened"]},
        "moments": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "required": ["turn", "mood", "note"],
            "properties": {"turn": {"type": "integer"}, "mood": mood, "note": {"type": "string"}}}},
        "summary": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    }
    req = ["start", "end", "trajectory", "moments", "summary", "confidence"]
    if with_voice:
        props["voice"] = {"type": "object", "required": ["client_tone", "operator_tone", "moments", "summary"],
                          "properties": {
                              "client_tone": mood,
                              "operator_tone": {"type": "string", "enum": OPERATOR_TONES},
                              "moments": {"type": "array", "maxItems": 4, "items": {
                                  "type": "object", "required": ["time", "mood", "cue"],
                                  "properties": {"time": {"type": "string"}, "mood": mood,
                                                 "cue": {"type": "string"}}}},
                              "summary": {"type": "string"}}}
        req.append("voice")
    return {"type": "object", "required": req, "properties": props}


def _prompt(conv: dict, with_voice: bool) -> str:
    return (_RULES + (_AUDIO_RULES if with_voice else "")
            + f"\n\nКанал: {conv.get('channel')}, язык: {conv.get('language')}\nТранскрипт:\n"
            + prompts.format_transcript(conv["transcript"]))


async def analyze(conv: dict) -> tuple[dict | None, dict | None, str | None]:
    """Returns (mood, usage, error). Never raises."""
    if not settings.mood_enabled:
        return None, None, "disabled"
    rec, audio_err = None, None
    if settings.mood_audio and conv.get("audio_url"):
        try:
            rec = await audio.fetch_bytes(conv["audio_url"], settings.audio_max_mb * 1_000_000)
        except Exception as e:  # noqa: BLE001 - fall back to text-only
            audio_err = str(e)
            log.warning("mood: no audio for %s: %s", conv.get("id"), e)
    with_voice = rec is not None
    prompt = _prompt(conv, with_voice)
    contents = [types.Part.from_bytes(data=rec[0], mime_type=rec[1]), prompt] if with_voice else None
    n = len(conv["transcript"])
    try:
        data, usage = await gemini.generate_json(prompt, _schema(with_voice), contents=contents)
    except Exception as e:  # noqa: BLE001 - mood is optional
        return None, None, str(e)
    for m in data.get("moments", []):
        t = m.get("turn")
        ok = isinstance(t, int) and 0 <= t < n
        m["turn"] = t if ok else None
        m["timestamp"] = conv["transcript"][t].get("timestamp") if ok else None
    data["source"] = "text+audio" if with_voice else "text"
    if audio_err:
        data["audio_error"] = audio_err
    return data, usage, None
