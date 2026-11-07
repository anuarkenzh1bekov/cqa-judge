"""Gemini client: structured JSON output + usage accounting."""
import asyncio
import json
import logging

from google import genai
from google.genai import types

from ..config import settings

log = logging.getLogger(__name__)
_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


class LLMError(RuntimeError):
    pass


async def generate_json(prompt: str, schema: dict, system: str | None = None, retries: int = 2,
                        validate=None) -> tuple[dict, dict]:
    """Returns (parsed_json, usage). `validate(data)` may raise to trigger a retry."""
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=0.0,
        seed=7,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        **({"thinking_config": types.ThinkingConfig(thinking_level=settings.gemini_thinking.upper())}
           if settings.gemini_thinking else {}),
    )
    usage = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "calls": 0}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = await client().aio.models.generate_content(model=settings.gemini_model, contents=prompt, config=cfg)
            um = resp.usage_metadata
            usage["calls"] += 1
            if um:
                usage["input_tokens"] += um.prompt_token_count or 0
                usage["output_tokens"] += um.candidates_token_count or 0
                usage["thinking_tokens"] += um.thoughts_token_count or 0
            data = json.loads(resp.text)
            if validate:
                validate(data)
            return data, usage
        except Exception as e:  # noqa: BLE001 - retry on API errors, bad JSON, failed validation
            last_err = e
            log.warning("gemini attempt %s failed: %s", attempt + 1, e)
            await asyncio.sleep(1.5 * (attempt + 1))
    raise LLMError(f"Gemini failed after {retries + 1} attempts: {last_err}")


def cost_usd(usage: dict) -> float:
    out = usage.get("output_tokens", 0) + usage.get("thinking_tokens", 0)
    return (usage.get("input_tokens", 0) * settings.gemini_price_in_per_m
            + out * settings.gemini_price_out_per_m) / 1_000_000
