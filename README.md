# CQA Judge — Conversation Quality Analytics

Prototype for the Freedom Broker hackathon: scoring an operator's work against a configurable checklist (RU / KZ / EN, chats and calls),
with explanations that link to the exact message and to the moment in the recording, appeals with review, operator feedback and analytics.
The interface is in Russian; Russian labels are shown in quotes with their English meaning.

![CQA Judge: from a conversation to an appeal decision](docs/demo.gif)

*A real run of the interface in demo mode: open a conversation, jump from "Требуют проверки" (Needs review) to the evidence, dispute a score, and see the outcome and the new total in one line.*

## Run with Docker

```bash
cp .env.example .env   # fill in the keys and DATASET_API_URL
docker compose up -d --build
```

Open http://localhost:8000. The SQLite database lives in the `cqa-data` volume and survives restarts; keys are read from `.env`
at startup and are not baked into the image. Stop with `docker compose down` (data is kept), wipe the data with
`docker compose down -v`.

On first start with an empty database, the 65 DEV conversations are loaded from `datasets/DEV.json` (dialogs only, no
scores: evaluate them from the interface, "Оценить новые" or a conversation's "Оценить"). Set `SEED_DATASET=` in `.env`
to disable this.

To move an already evaluated local database into the container (all scores, appeals, checklist versions):

```bash
docker compose stop
docker run --rm -v cqa-judge_cqa-data:/data -v "$PWD/backend:/src:ro" alpine \
  sh -c 'cp -f /src/cqa.db /data/cqa.db && rm -f /data/cqa.db-wal /data/cqa.db-shm && chown 1000:1000 /data/cqa.db'
docker compose up -d
```

## Run without Docker

Requires Python 3.10+.

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in the keys and DATASET_API_URL
python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000: the backend serves the interface from `web/` itself.

1. "Диалоги" (Conversations) → "Оценить новые" (Evaluate new) → `group_id` (for example `DEV`) → the set is loaded from the organizers' API and evaluated.
2. Conversation view: score, gross errors, operator feedback, and for every criterion the answer, points, explanation,
   links to messages and the opinions of Gemini and Jev. For calls there is a player, and clicking a message seeks the recording.
3. "Оспорить" (Dispute) → an appeal. The "Проверяющий" (Reviewer) switch or the "Апелляции" (Appeals) screen → a decision (you can ask the AI
   to re-check) → the total is recalculated and the original score is kept.
4. "Чек-лист" (Checklist) → change or replace a criterion → "Сохранить и применить" (Save and apply) to the set. A new version is saved.
5. "Аналитика" (Analytics) → average scores by language, channel, operator and criterion, model agreement, cost, how many
   conversations the AI is confident about, calibration against reviewers, and an Excel / CSV report for managers.
6. "Сравнить версии" (Compare versions, on the checklist screen) → the same conversations scored by two checklist versions.
7. In a conversation: "Следующий" (Next, key `N`) opens the next conversation in the list.

**The judge learns from reviewers.** When a reviewer changes an answer through an appeal, the correction (with the reason)
goes into the prompt of that criterion for later evaluations (`CALIBRATION_EXAMPLES` latest per criterion, the conversation
being evaluated is excluded). The analytics screen shows where reviewers agree with the AI and how it changes.

Swagger: http://localhost:8000/docs · API description: [API.md](API.md) · Demo without a backend: http://localhost:8000/?demo=1

## How the evaluation works

```
conversation ─┬─► Gemini  (facts about the conversation, an answer per criterion, explanation, evidence messages, feedback)
              └─► Jev     (an independent answer per criterion + a calibrated probability)
                       │
                       ▼  merge per criterion
   agree ─► Gemini's answer          adjacent scale steps ─► Gemini's answer
   disagree, Jev confident (≥0.8)    ─► Gemini re-checks the criterion, flagged "disputed"
   disagree, Jev not confident       ─► Gemini's answer, flagged "needs review"
                       │
                       ▼  code (not a model)
   quote check against the transcript → N/A rules → points by weight → N/A redistribution → total (2 decimals) → gross errors
```

- Prompts and response schemas are generated from the checklist config: a new or replaced criterion works without code changes.
- Every evaluation really calls the models (no cache by `conversation_id`) and stores a snapshot of the checklist it was made with.
- Jev is optional: without a key, or on error, the evaluation runs on Gemini only.

## Tests

```bash
cd backend
python -m pytest -q
```

25 offline tests (no network or keys, the models are replaced with stubs): scoring and N/A, merging Gemini and Jev answers
(agreement, re-check, the "needs review" flag, Jev failure), validation of message links, the full path through the API
(upload → evaluation → appeal → decision → recalculation → statistics), criterion replacement and checklist validation.

### Run on a random sample (real models)

```bash
cd backend
python scripts/eval_sample.py --n 12 --runs 2            # random sample, stratified by language and channel
python scripts/eval_sample.py --n 12 --runs 2 --seed 7   # reproducible sample
```

The report is saved to `backend/reports/`. DEV has no ground truth, so the report shows correctness (valid answers,
real message links), consistency with the N/A rules, stability (the same conversation twice) and model agreement.
To measure accuracy, label the sample by hand:

```bash
python scripts/eval_sample.py --make-gold-template eval/gold.json --n 15   # template with empty answers
python scripts/eval_sample.py --gold ../eval/gold.json                      # per-criterion accuracy and total MAE
```

`eval/gold.json` holds hand labels for 14 DEV conversations (7 RU, 3 KZ, 3 EN, 1 call), made by reading each
transcript against the checklist PDF **without looking at the system's answers**. They are an independent second
opinion, not the organizers' ground truth; every label has a note explaining it. Result
(`backend/reports/eval_DEV_20261107_160116.md`): **94% per-criterion agreement, total-score MAE 4.38**. The remaining
disagreements are systematic: the system gives 20 for consultation when a secondary question was left without a next
step (the PDF says 15), and sometimes N/A for needs discovery on account-specific requests. Tightening the guidance for
these two criteria was tried and made agreement worse (92%), so it was reverted.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | Gemini (default `gemini-3.8-flash`) |
| `TYPESAFE_API_KEY`, `JEV_MODEL`, `JEV_ENABLED` | Jev by TypeSafe AI (`jev-latest`) |
| `JEV_ADJUDICATE_THRESHOLD` | Jev probability above which a disagreement is sent for a re-check (0.8) |
| `DATASET_API_URL` | the organizers' GET link **without** `group_id` (it contains a signature, do not commit it) |
| `GEMINI_PRICE_IN_PER_M`, `GEMINI_PRICE_OUT_PER_M` | price per 1M tokens for cost estimates (defaults: Gemini 3.8 Flash paid tier, $0.75 in / $3.75 out, through 2026) |
| `MAX_CONCURRENCY` | parallel evaluations in a batch (4) |
| `DATABASE_URL` | defaults to SQLite `backend/cqa.db` |

## Cost of one evaluation

Models: **Gemini 3.8 Flash** (`gemini-3.8-flash`, paid Standard tier: $0.75 / 1M input, $3.75 / 1M output including
thinking tokens, valid through 2026-12-31; doubles from 2027-01-01) and **Jev** (`jev-1.14.0`, $0.042 / 1M input, output free).

One evaluation = one Gemini call (~3–4k input tokens, ~1.5k output + ~1.5–3k thinking), a second Gemini call only if the
models disagree confidently, plus one Jev call (~6k input tokens). Measured on 74 DEV evaluations: **≈ $0.016 per
conversation on average** (min $0.008, max $0.032); Jev adds about $0.0003 of that. The 10 control transcripts cost about
$0.16. Prices are configurable in `.env`; the actual cost of each evaluation is shown in the conversation view and on the
"Аналитика" (Analytics) screen.
The actual cost of each evaluation is shown in the conversation view and on the "Аналитика" (Analytics) screen.

## Structure

| Path | What it is |
|---|---|
| `backend/app/checklist.py` | checklist schema + the starter checklist from the PDF |
| `backend/app/scoring.py` | deterministic scoring (tests: `cd backend && python -m pytest -q`) |
| `backend/app/prompts.py` | prompts and JSON schemas, generated from the checklist |
| `backend/app/llm/` | Gemini and Jev clients |
| `backend/app/pipeline.py` | evaluation: Gemini ∥ Jev → merge → quote check → points |
| `backend/app/routers/` | API: conversations, checklists, evaluations, appeals, stats |
| `backend/tests/` | offline tests (`python -m pytest -q`) |
| `backend/scripts/eval_sample.py` | random-sample run with a report |
| `Dockerfile`, `docker-compose.yml` | image and one-command startup |
| `datasets/DEV.json` | copy of the DEV set (65 conversations). Signed links to real call recordings are removed (`has_audio: true`); if the organizers' API is down, import by `group_id` falls back to this file. Refresh: `python backend/scripts/download_dataset.py --group DEV` |
| `web/` | interface in plain HTML, CSS and JavaScript, no build step; `web/js/backend.js` talks to the API |
| `web/dist/cqa-webresource.html` | the whole interface in one file for Dynamics 365 (`python web/build.py`) |

Interface parameters (`?api=`, `?embed=1`, `?theme=`, `?demo=1`) and Dynamics 365: [web/README.md](web/README.md).
