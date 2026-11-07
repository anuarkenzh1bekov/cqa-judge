"""Call recordings. The organizers' audio_url is an HTML player page whose <source> holds a short-lived (1 h)
signed mp3 link, so it is resolved on every use."""
import html
import re
from pathlib import Path

import httpx

from .config import settings

_SRC_RE = re.compile(r"""<source[^>]+src=["']([^"']+)["']""", re.I)


LOCAL = "local:"  # audio_url of an uploaded recording: "local:<file name in AUDIO_DIR>"


class AudioError(RuntimeError):
    pass


def local_path(url: str) -> Path | None:
    """Path of an uploaded recording, or None for a remote URL. Refuses anything outside AUDIO_DIR."""
    if not (url or "").startswith(LOCAL):
        return None
    root = Path(settings.audio_dir).resolve()
    p = (root / url[len(LOCAL):]).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise AudioError("recording file not found")
    return p


async def resolve(http: httpx.AsyncClient, url: str) -> str:
    r = await http.get(url)
    if r.status_code != 200:
        raise AudioError(f"audio page returned {r.status_code}")
    if r.headers.get("content-type", "").startswith("audio/"):
        return url
    m = _SRC_RE.search(r.text)
    if not m:
        raise AudioError("no audio source found on the player page")
    return html.unescape(m.group(1))


async def fetch_bytes(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Downloads the whole recording (for sending to the model). Returns (bytes, mime type)."""
    p = local_path(url)
    if p:
        if p.stat().st_size > max_bytes:
            raise AudioError(f"recording is larger than {max_bytes // 1_000_000} MB")
        from .transcribe import MIME
        return p.read_bytes(), MIME.get(p.suffix.lower(), "audio/mp3")
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
        src = await resolve(http, url)
        async with http.stream("GET", src) as resp:
            if resp.status_code != 200:
                raise AudioError(f"audio upstream returned {resp.status_code}")
            mime = resp.headers.get("content-type", "audio/mpeg").split(";")[0]
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf += chunk
                if len(buf) > max_bytes:
                    raise AudioError(f"recording is larger than {max_bytes // 1_000_000} MB")
    return bytes(buf), mime
