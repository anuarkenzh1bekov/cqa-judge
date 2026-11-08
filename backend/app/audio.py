"""Call recordings. The organizers' audio_url is an HTML player page whose <source> holds a short-lived (1 h)
signed mp3 link, so it is resolved on every use."""
import hashlib
import html
import re
import uuid
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


def _cache_file(url: str) -> Path:
    return Path(settings.audio_dir) / "cache" / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".mp3")


def cached_path(url: str) -> Path | None:
    """Local copy of a remote recording if it was downloaded before."""
    p = _cache_file(url)
    return p if p.is_file() else None


async def cache_remote(url: str, max_bytes: int = 100_000_000) -> Path:
    """Downloads a remote recording once and keeps it in AUDIO_DIR/cache, so playback and seeking are served
    from disk instead of going to the organizers' server on every Range request."""
    p = cached_path(url)
    if p:
        return p
    data, _ = await fetch_bytes(url, max_bytes)
    target = _cache_file(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f".{uuid.uuid4().hex}.part")
    tmp.write_bytes(data)
    tmp.replace(target)  # atomic: a concurrent request never sees a half-written file
    return target


async def fetch_bytes(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Downloads the whole recording (for sending to the model). Returns (bytes, mime type)."""
    p = local_path(url) or cached_path(url)
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
