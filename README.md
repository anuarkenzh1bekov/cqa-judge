# CQA Judge

Scores operator chats and calls against a checklist you can edit. Every answer points to the message it rests on, and for calls to the moment in the recording. Built for the Freedom Broker hackathon. The interface is in Russian.

![CQA Judge demo](docs/demo.gif)

The clip, left to right: the reviewer's list, a card with a gross error, an evaluation streaming in, rejecting an appeal with a written reason, an operator's own dialogs, and a coaching plan built from the reviewer's comments.

## Run

With Docker:

```bash
cp .env.example .env   # fill in the keys and DATASET_API_URL
docker compose up -d --build
```

Without Docker (Python 3.10+):

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env
python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000. The backend serves `web/` itself. Swagger is at `/docs`, the API is described in [API.md](API.md), and `/?demo=1` runs the interface without a backend.

On first start an empty database gets the 65 DEV conversations from `datasets/DEV.json`, unscored. Press "Оценить новые" (Evaluate new) to score them. Set `SEED_DATASET=` to skip the seeding. In Docker the SQLite file lives in the `cqa-data` volume, `docker compose down -v` wipes it, and to move a local database in:

```bash
docker compose stop
docker run --rm -v cqa-judge_cqa-data:/data -v "$PWD/backend:/src:ro" alpine \
  sh -c 'cp -f /src/cqa.db /data/cqa.db && rm -f /data/cqa.db-wal /data/cqa.db-shm && chown 1000:1000 /data/cqa.db'
docker compose up -d
```

## What it does

- Scores chats and calls in RU, KZ and EN. Criteria are edited in the interface, with no code change, and every evaluation keeps a snapshot of the checklist version it used. Versions have names (v1, v2 or your own) and can be compared on the same conversations.
- Explains each answer with links to messages. Call recordings play in the card and a click on a message seeks to it. An uploaded recording is transcribed by Gemini with personal data masked.
- Streams the evaluation: the card fills in while the model is still writing.
- Has two roles, switched in the header. An operator sees only their own dialogs, can appeal a criterion once the reviewer publishes the evaluation, reads the checklist without editing it, sees a list of their appeals (an open one can be deleted) and their own analytics. A reviewer comments, publishes, edits the checklist and decides appeals: accept with a new answer, or reject with a written reason the operator sees.
- Recalculates the total after an appeal and keeps the original score. A reviewer's correction goes into the prompt of that criterion for later evaluations, and the analytics screen shows where reviewers agree with the AI.
- Puts a sparkle button in text fields (appeal, decision, comment, criterion wording). It improves what is written, or drafts a text from the criterion and the dialog when the field is empty.
- Builds a coaching plan per operator, mostly from the reviewer's published comments and appeal decisions, then from the weakest criteria with real quotes and a colleague's full-marks dialog. Code picks the facts and Gemini writes the advice. The plan is rebuilt after every new dialog, comment or decision, and a rules-only plan appears when the model is unavailable.
- Reads the client's mood per dialog (from the recording's tone as well, for calls). The mood never changes the score.
- Treats the dialog as data. Turns that try to instruct the evaluator ("ignore the rules", "give 100 points") are detected in RU, KZ and EN, fenced off in the prompts and shown on the card, and the criteria that rest on them are flagged for review. Scoring is plain code and every quote is checked against the transcript, so a fooled model still cannot move the score.
- Shows analytics by language, channel, operator and criterion, exports one Excel file with every dialog, justification, appeal and gross error, and writes the organizers' `results.json`.

## How scoring works

```
conversation ─┬─► Gemini  (facts, an answer per criterion, explanation, evidence messages, feedback)
              └─► Jev     (an independent answer per criterion + a calibrated probability)
                       │
                       ▼  merge per criterion
   agree ─► Gemini's answer          adjacent scale steps ─► Gemini's answer
   disagree, Jev confident (≥0.8)    ─► Gemini re-checks the criterion, flagged "disputed"
   disagree, Jev not confident       ─► Gemini's answer, flagged "needs review"
                       │
                       ▼  code, not a model
   quote check → N/A rules → points by weight → N/A redistribution → total → gross errors
```

Prompts and schemas are generated from the checklist, and every evaluation calls the models for real, with no cache by conversation id. Jev is optional: without a key the evaluation runs on Gemini alone. `eval/synthetic.json` holds edge cases written by hand, run with `python backend/scripts/run_synthetic.py` against a running server (87 of 88 criteria match our labels, the miss is a borderline case flagged for review).

## Tests and accuracy

```bash
cd backend
python -m pytest -q
```

71 offline tests with the models stubbed: scoring, merging, the API flow from upload to appeal to statistics, streaming, the injection guard, coaching and the AI text helper.

To score a random sample with the real models, or to measure accuracy against hand labels:

```bash
python scripts/eval_sample.py --n 12 --runs 2 --seed 7
python scripts/eval_sample.py --make-gold-template eval/gold.json --n 15
python scripts/eval_sample.py --gold ../eval/gold.json
```

`eval/gold.json` has hand labels for 14 DEV conversations (7 RU, 3 KZ, 3 EN, 1 call), made from the transcripts and the checklist PDF without looking at the system's answers. They are a second opinion, not the organizers' truth. The system agrees on 94% of criteria, with a total-score error of 4.38 points (`backend/reports/eval_DEV_20261107_160116.md`). Most of the misses come from two criteria: consultation (the system gives 20 where the PDF says 15 when a secondary question got no next step) and needs discovery (sometimes N/A on account-specific requests). Tightening the guidance for them lowered agreement to 92%, so it was reverted.

## Configuration

Set in `.env`:

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | Gemini, default `gemini-3.8-flash` |
| `TYPESAFE_API_KEY`, `JEV_MODEL`, `JEV_ENABLED` | Jev by TypeSafe AI |
| `JEV_ADJUDICATE_THRESHOLD` | Jev probability above which a disagreement is re-checked (0.8) |
| `DATASET_API_URL` | the organizers' link without `group_id`. It contains a signature, do not commit it |
| `STREAM_ENABLED`, `COACHING_ENABLED` | live evaluation and the coaching plan, both on by default |
| `MOOD_ENABLED`, `MOOD_AUDIO` | client mood, and whether it listens to the recording |
| `MAX_CONCURRENCY` | parallel evaluations in a batch (4) |
| `GEMINI_PRICE_IN_PER_M`, `GEMINI_PRICE_OUT_PER_M` | prices for cost estimates ($0.75 and $3.75 per 1M tokens) |
| `DATABASE_URL` | defaults to SQLite `backend/cqa.db` |

## Cost and time

Gemini 3.8 Flash costs $0.75 per 1M input tokens and $3.75 per 1M output tokens including thinking, through 2026-12-31 (double from 2027-01-01). Jev costs $0.042 per 1M input tokens. One evaluation is the main Gemini call, Jev and the mood call in parallel, and a Gemini re-check only when the models disagree confidently. Measured on 108 evaluations (DEV plus our edge cases, 2026-11-07):

| | cost per dialog | time (median / p90) |
|---|---|---|
| chat | $0.015 average | 20 s / 41 s |
| call with a transcript | $0.020 average, up to $0.035 with tone analysis | 20 s / 29 s |
| call from a recording | about $0.05 for 5 to 6 minutes | about 50 s |

With 4 dialogs in parallel the 65 DEV dialogs take 6.5 to 7 minutes and about $0.95. At 10,000 dialogs a month that is about $150, or $300 after the 2027 price change. The real cost and time of each evaluation are stored and shown in the analytics screen and the Excel file.

## Structure

| Path | What it is |
|---|---|
| `backend/app/` | FastAPI: `pipeline.py` (evaluation), `scoring.py` (deterministic points), `prompts.py`, `guard.py` (injection defence), `coaching.py`, `live.py` (streaming), `routers/`, `llm/` (Gemini and Jev clients) |
| `backend/tests/` | offline tests |
| `backend/scripts/` | sample runs, dataset download, `results.json` export |
| `web/` | the interface in plain HTML, CSS and JavaScript, no build step. Parameters and Dynamics 365 are in [web/README.md](web/README.md) |
| `web/dist/cqa-webresource.html` | the whole interface in one file for Dynamics 365, built with `python web/build.py` |
| `datasets/DEV.json` | the DEV set, 65 conversations, with signed audio links removed. Import by `group_id` falls back to it when the organizers' API is down |
| `Dockerfile`, `docker-compose.yml` | image and one-command start |

## Submission file

The organizers' format 1.0 is built from the latest evaluation of each conversation with final answers after appeals. Turn numbers are 1-based, also inside explanations. A conversation that was not evaluated is written as `status: "error"`, never as a zero.

```bash
cd backend
python scripts/export_results.py --group DEV --set dev --expect 65
python scripts/export_results.py --group <prod group_id> --set prod --expect 10
```

The script checks the file (all 8 criteria once, allowed values, unique ids, record count) and refuses to write a broken one. The same data with a `problems` list is at `GET /api/results?group=DEV&expect=65`.
