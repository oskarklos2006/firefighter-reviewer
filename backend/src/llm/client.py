# ─────────────────────────────────────────────────────────────
# client.py
# HTTP client for the LLM API. Uses the OpenAI-compatible
# /v1/chat/completions endpoint - works with Anthropic, OpenRouter,
# or any other provider by changing LLM_BASE_URL in .env.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import asyncio
import httpx
from config import settings


async def call_llm(prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # temperature=0.1 keeps outputs consistent across runs
    # while allowing minimal variation for natural language generation
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": settings.llm_max_tokens,
                    "messages": messages,
                    "temperature": 0.1,
                },
            )
            # Free tier providers rate limit aggressively - back off and retry
            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    raise RuntimeError("LLM rate limit exceeded after 3 retries")