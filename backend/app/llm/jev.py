"""Jev (TypeSafe AI System One model): independent second opinion with calibrated probabilities.
API: POST https://api.typesafe.ai/v1/systemone  (Authorization: Bearer <key>)."""
import asyncio
import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)
URL = "https://api.typesafe.ai/v1/systemone"


def enabled() -> bool:
    return settings.jev_enabled and bool(settings.typesafe_api_key)


async def ask(state, questions: dict, retries: int = 2) -> tuple[dict, dict]:
    """Returns ({question: answer_obj}, usage). Raises on persistent failure."""
    body = {"model": settings.jev_model, "state": state, "questions": questions}
    headers = {"Authorization": f"Bearer {settings.typesafe_api_key}"}
    last = None
    async with httpx.AsyncClient(timeout=60) as http:
        for attempt in range(retries + 1):
            try:
                r = await http.post(URL, json=body, headers=headers)
                if r.status_code in (429, 529) or r.status_code >= 500:
                    wait = float(r.headers.get("retry-after", 1.5 * (attempt + 1)))
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
                    await asyncio.sleep(min(wait, 10))
                    continue
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                data = r.json()
                usage = dict(data.get("usage") or {})
                usage["model"] = data.get("model")
                return data["answers"], usage
            except httpx.HTTPError as e:
                last = str(e)
                await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Jev failed: {last}")


def cost_usd(usage: dict) -> float:
    return usage.get("input_tokens", 0) * settings.jev_price_in_per_m / 1_000_000
