# CQA: interface

Plain HTML, CSS and JavaScript. No bundler, no external dependencies.

## Run

Any static file server works. Double-clicking the file will not: browsers block loading scripts from disk.

```bash
python -m http.server 5173 --directory web
```

Open http://localhost:5173

## URL parameters

| Parameter | What it does |
|---|---|
| `?embed=1` | embedded mode: hides the logo, for Dynamics 365 |
| `?api=https://host` | backend address. Default: the same origin the page is served from (the backend serves `web/` at http://localhost:8000), or `http://localhost:8000` when opened from the static server on :5173 |
| `?demo=1` | demo mode without a backend: four built-in conversations, state kept in the browser |
| `?theme=dark` or `light` | theme |

## Dynamics 365

```bash
python web/build.py
```

This creates `web/dist/cqa-webresource.html`: one file with styles, scripts and the logo inlined. Upload it as an HTML web resource and open it in a form frame, for example `...cqa-webresource.html?embed=1&api=https://host`.

## Structure

```
index.html      markup
css/styles.css  styles, light and dark themes
js/config.js    URL parameters
js/api.js       backend calls (see ../API.md)
js/backend.js   loads data from the backend into the screens and sends actions back
js/data.js      data and browser persistence
js/scoring.js   scoring: weights, N/A, redistribution, sections
js/utils.js     helpers
js/router.js    navigation between screens
js/list.js, card.js, checklist.js, appeals.js, stats.js   screens
js/app.js       shared events, evaluation dialog, theme, startup
assets/         logo
build.py        single-file build
```
