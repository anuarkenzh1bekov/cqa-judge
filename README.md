# cqa-judge

Interface for scoring operator performance in customer conversations (Conversation Quality Analytics, Freedom Broker CQA Hackathon).

An eight-criterion checklist, a per-criterion verdict with a quoted piece of evidence, a total score that redistributes weight when a criterion is N/A, appeals with a reviewer decision, and a checklist editor. Chats in Russian, Kazakh and English are supported, as well as voice calls. The interface itself is in Russian.

## Run

Requires Python 3 (any static file server works):

```bash
python -m http.server 5173 --directory web
```

Open http://localhost:5173

Double-clicking `index.html` will not work: browsers block loading scripts from disk.

## What is inside

| Path | What it is |
|---|---|
| `web/` | the interface in plain HTML, CSS and JavaScript, no build step |
| `web/dist/cqa-webresource.html` | the whole interface in a single file, ready to upload to Dynamics 365 as an HTML web resource |
| `web/build.py` | builds that file: `python web/build.py` |

More on structure, URL parameters (`?embed=1`, `?api=…`, `?theme=…`) and Dynamics 365: [web/README.md](web/README.md).

## Data

Conversations and results shown in the interface are demo data: four conversations (RU, EN, KZ and a voice call) with pre-filled results.
