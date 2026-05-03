from __future__ import annotations
import asyncio
import httpx
from src.config import settings


async def call_llm(prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

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
            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"Rate limited, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    raise RuntimeError("LLM rate limit exceeded after 3 retries")