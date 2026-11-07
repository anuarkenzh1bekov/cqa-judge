# CQA Judge — API для фронтенда

База: `http://localhost:8000`. Интерактивная документация (Swagger): `http://localhost:8000/docs`.
CORS открыт (`CORS_ORIGINS` в `.env`). Авторизации нет. Все даты — ISO 8601 UTC.

## Обозначения ответов

| Тип критерия | Возможные `answer` | Как показывать |
|---|---|---|
| `binary` | `yes`, `no`, `na` (если `na_allowed`) | Да / Нет / N/A |
| `scale` | ступени шкалы строкой: `"20"`, `"15"`… и `na` | число / N/A |
| `flag` (грубые ошибки) | `yes`, `no` | Выявлены / Нет. Баллов нет, отображать отдельно |

`agreement` (согласие двух моделей по критерию):
`agree` — совпали; `minor` — соседние ступени шкалы; `disputed` — разошлись, Gemini перепроверил (`adjudication`);
`review` — разошлись, Jev не уверен; `gemini_only` — Jev выключен/недоступен.
`needs_review: true` + `review_reasons` (`models_disagree`, `low_confidence`, `no_evidence`, `invalid_evidence_dropped`) —
подсветить как «спорный критерий, проверить».

---

## 1. Диалоги

### `POST /api/datasets/import`
Загрузить набор из API организаторов. `{"group_id": "DEV"}` → `{"group_id","imported","conversation_ids"}`.
На контрольном этапе — другой `group_id`.

### `POST /api/conversations`
Загрузка своих транскриптов (формат как у API организаторов):
```json
{"group": "UPLOAD", "records": [{"conversation_id": "x1", "channel": "agent chat", "language": "RU",
  "transcript": [{"timestamp": "00:02", "speaker": "operator", "text": "Здравствуйте!"}], "audio_url": null}]}
```

### `GET /api/conversations?group=&language=&channel=`
Список для таблицы: `id, group, channel, language, has_audio, turns, preview, latest_evaluation` (сводка последней оценки
или `null`).

### `GET /api/conversations/{id}`
`transcript` (у каждой реплики есть `index` — по нему работают ссылки-доказательства), `audio_url`, список `evaluations`.

### `GET /api/conversations/{id}/audio`
Запись звонка в mp3 (бэкенд каждый раз берёт свежую ссылку со страницы-плеера организаторов — их ссылки живут 1 час).
Поддерживает Range, поэтому перемотка работает: `<audio src="http://localhost:8000/api/conversations/p4-ru-001/audio">`,
затем `audio.currentTime = секунды`. Время реплики звонка — ISO; смещение для перемотки ≈
`timestamp(реплики) − timestamp(первой реплики)` (запись может начинаться чуть раньше/позже — проверьте на p4-ru-001).

---

## 2. Чек-листы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/checklists` | все |
| GET | `/api/checklists/active` | активный (используется по умолчанию) |
| GET | `/api/checklists/default-template` | исходный чек-лист из PDF (кнопка «сбросить») |
| GET | `/api/checklists/{id}` | один |
| POST | `/api/checklists?activate=true` | создать |
| PUT | `/api/checklists/{id}` | изменить (старые оценки не меняются: у каждой свой снимок чек-листа) |
| POST | `/api/checklists/{id}/activate` | сделать активным |
| POST | `/api/checklists/{id}/duplicate` | копия |
| DELETE | `/api/checklists/{id}` | удалить (не активный) |
| GET | `/api/checklists/{id}/prompt-preview?conversation_id=` | точный промпт и вопросы Jev (прозрачность) |

Тело для POST/PUT:
```json
{
  "name": "Мой чек-лист",
  "description": "…",
  "criteria": [
    {"key": "c01_contact", "section": "Начало и понимание запроса", "name": "Установление контакта",
     "type": "binary", "weight": 10, "na_allowed": false, "na_condition": null,
     "description": "Да — оператор поздоровался …", "guidance": "необязательные пояснения для модели"},
    {"key": "c04_consultation", "section": "…", "name": "Корректная и полная консультация",
     "type": "scale", "weight": 20, "na_allowed": true, "na_condition": "Чат закончился до …",
     "description": "…", "scale": [{"value": 20, "description": "…"}, {"value": 0, "description": "…"}]},
    {"key": "c08_gross", "name": "Грубые ошибки", "type": "flag", "weight": 0, "description": "…"}
  ]
}
```
Правила валидации (422 при нарушении): `key` — латиница/цифры/`_-`, уникальный; `scale` ≥ 2 ступеней, только у `scale`;
`flag` — вес 0; при `na_allowed: true` нужен `na_condition`. Сумма весов не обязана быть 100 — итог всё равно
нормируется к 100.

---

## 3. Оценка

### `POST /api/evaluations` (синхронно, 20–40 с)
`{"conversation_id": "p1-ru-001", "checklist_id": null, "with_feedback": true}` → полная карточка (как GET ниже).
`checklist_id: null` = активный чек-лист.

### `POST /api/evaluations/batch` (фон) → `202`
`{"group": "DEV"}` или `{"conversation_ids": ["…"], "checklist_id": 2}` → `{"batch_id", "evaluation_ids", "total"}`.
Прогресс: `GET /api/batches/{batch_id}` → `{total, pending, running, done, error, finished, evaluations:[сводки]}`.
Опрашивать раз в 2–3 с.

### `GET /api/evaluations?conversation_id=&checklist_id=&status=&batch_id=`
Сводки: `id, conversation_id, status, initial_total, final_total, gross_error, operator_name, needs_review,
open_appeals, cost_usd, duration_ms, …`

### `GET /api/evaluations/{id}` — карточка
```jsonc
{
  "id": 12, "status": "done", "initial_total": 78.46, "final_total": 85.0, "gross_error": false,
  "operator_name": "Нина", "cost_usd": 0.0123, "duration_ms": 38035,
  "conversation": {"id": "p1-ru-005", "channel": "agent chat", "language": "RU", "has_audio": false,
                   "transcript": [{"index": 0, "timestamp": "00:00", "speaker": "client", "text": "…"}]},
  "facts": {"client_request": "…", "request_type": "general_info", "identity_required": false, "ending": "…"},
  "results": [{
    "key": "c07_closing", "name": "Завершение", "section": "…", "type": "binary", "weight": 5,
    "answer": "yes",                 // исходная итоговая оценка системы
    "explanation": "Завершение — Да. …",
    "evidence": [{"index": 15, "timestamp": "07:16", "speaker": "operator", "text": "…"}],
    "checked_range": [9, 15],        // проверенный участок (для «Нет» по пропуску и N/A)
    "confidence": "high",
    "points": 7.69, "max_points": 7.69, "applicable": true,   // баллы после перераспределения N/A (из 100)
    "gemini": {"answer": "yes", "explanation": "…", "confidence": "high"},
    "jev": {"answer": "yes", "probability": 1.0, "probabilities": {"yes": 1.0, "no": 0.0, "na": 0.0}},
    "agreement": "agree", "adjudicated": false, "adjudication": null,
    "needs_review": false, "review_reasons": [],
    "final_answer": "yes", "final_points": 7.69, "final_max_points": 7.69,   // после апелляций
    "appeals": []
  }],
  "initial_score": {"total": 78.46, "gross_error": false, "sections": {"<секция>": {"score_pct": 60.0}}, "criteria": {}},
  "final_score":   {"total": 85.0, "…": "…"},
  "feedback": {"summary": "…",
               "strengths":    [{"text": "…", "turn": 9, "timestamp": "02:52"}],
               "improvements": [{"text": "…", "turn": 11, "criterion_key": "c06_management",
                                 "example_phrase": "…", "timestamp": "04:23"}]},
  "appeals": [], "models": {"gemini": "gemini-3.8-flash", "jev": "jev-1.14.0"},
  "checklist": {"id": 1, "name": "…", "criteria": []}
}
```
Ссылка на реплику: `evidence[].index` / `feedback.*.turn` → прокрутка к `transcript[index]`.

Настроение клиента — `facts.client_mood` (отдельный вызов, на балл не влияет; `null`, если анализ не удался — причина в `usage.mood_error`):
```json
{"start": "anxious", "end": "positive", "trajectory": "improved", "confidence": "high", "summary": "…",
 "moments": [{"turn": 16, "mood": "anxious", "note": "…", "timestamp": "…"}],
 "source": "text+audio",
 "voice": {"client_tone": "anxious", "operator_tone": "neutral", "summary": "…",
           "moments": [{"time": "05:37", "mood": "anxious", "cue": "нервный смешок, быстрый темп"}]}}
```
`mood`: calm · positive · confused · anxious · irritated · angry. `voice` есть только у звонков с доступной записью.
N/A: `answer == "na"`, `applicable: false`, причина — в `explanation`.

### `POST /api/evaluations/{id}/rerun` → `{"evaluation_id"}` (фон)
### `GET /api/evaluations/{id}/export` — плоский JSON для CRM (Dynamics 365), только экспорт.

---

## 4. Апелляции

| Метод | Путь | Тело / ответ |
|---|---|---|
| POST | `/api/evaluations/{id}/appeals` | `{"criterion_key", "comment", "author"}` → апелляция с контекстом. 409, если по критерию уже есть открытая |
| GET | `/api/appeals?status=open` | очередь проверяющего |
| GET | `/api/appeals/{id}` | апелляция + `criterion_result`, `fragment` (реплики вокруг доказательства), `initial_total`, `final_total` |
| POST | `/api/appeals/{id}/ai-review` | необязательная подсказка ИИ проверяющему: `ai_review: {suggested_answer, appeal_justified, explanation, evidence}`. Оценку не меняет |
| POST | `/api/appeals/{id}/decision` | `{"decision": "confirm" \| "change", "new_answer": "yes", "reason": "…", "reviewer": "…"}` → пересчитанные `initial_total`, `final_total`, `final_score` |

`status` апелляции: `open` → `confirmed` | `changed`. В карточке оценки у каждого критерия есть `appeals`, а исходная
(`answer`) и финальная (`final_answer`) оценки хранятся раздельно.

---

## 5. Аналитика (админка)

### `GET /api/stats?checklist_id=&group=`
По последней завершённой оценке каждого диалога, по ФИНАЛЬНЫМ баллам:
`overview` (кол-во, средний итог, грубые ошибки, спорные критерии, стоимость, время), `score_distribution`,
`by_language`, `by_channel`, `by_operator`, `by_criterion` (средний % балла, доля N/A, распределение ответов,
согласие моделей — отсортировано от самых проблемных), `model_agreement`, `appeals` (кол-во, `change_rate_pct`),
`lowest` (10 худших), `gross_errors`.

### `POST /api/conversations/transcribe` (multipart: `file`, необязательно `conversation_id`, `group`)
Запись звонка (mp3/wav/ogg/flac/aac/aiff, до 15 МБ) → Gemini распознаёт речь: роли operator/client/bot, время мм:сс,
персональные данные скрыты метками. Файл сохраняется (`AUDIO_DIR`, в Docker — том `/data/audio`) и играет в плеере,
диалог сохраняется как `voice call`. Ответ: `{conversation_id, language, turns, transcript, cost_usd, duration_ms}`.
Оценка — дальше обычным `POST /api/evaluations`.

### `GET /api/export/stats.xlsx?checklist_id=&group=` — та же аналитика в Excel. Листы: Сводка, Диалоги (ответ по каждому критерию, настроение, стоимость), Обоснования (каждый критерий каждого диалога с репликами-доказательствами), Критерии, Операторы, Грубые ошибки, Апелляции.
### `GET /api/operators` — список операторов со средним баллом.
### `GET /api/operators/{name}` — профиль: оценки, слабые критерии, собранные рекомендации и самые частые зоны роста.

### `GET /api/health` — модель Gemini, включён ли Jev.
