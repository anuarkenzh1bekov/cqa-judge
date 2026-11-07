"""Собирает интерфейс в один HTML-файл для загрузки в Dynamics 365 как web resource.

    python build.py

Результат: dist/cqa-webresource.html (стили, скрипты и логотип внутри файла).
"""
import pathlib
import re

root = pathlib.Path(__file__).parent
html = (root / "index.html").read_text(encoding="utf-8")
css = (root / "css" / "styles.css").read_text(encoding="utf-8")

html = html.replace('<link rel="stylesheet" href="css/styles.css">', f"<style>\n{css}\n</style>")
html = re.sub(r'<link rel="icon"[^>]*>\n?', "", html)


def inline_js(m):
    code = (root / m.group(1)).read_text(encoding="utf-8")
    assert "</script>" not in code, m.group(1)
    return f"<script>\n{code}\n</script>"


html = re.sub(r'<script src="(js/[^"]+)"></script>', inline_js, html)
assert "css/styles.css" not in html and 'src="js/' not in html

out = root / "dist"
out.mkdir(exist_ok=True)
target = out / "cqa-webresource.html"
target.write_text(html, encoding="utf-8", newline="\n")
print(f"{target.relative_to(root)}  {target.stat().st_size // 1024} КБ")
