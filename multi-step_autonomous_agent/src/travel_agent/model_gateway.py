import json
from typing import Protocol, cast

import httpx


class ModelGateway(Protocol):
    async def explain(self, prompt: str) -> str: ...

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, object],
    ) -> dict[str, object]: ...


class OllamaGateway:
    def __init__(
        self,
        model: str = "qwen3.5:latest",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 180.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def explain(self, prompt: str) -> str:
        content = await self._chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Explain the verified travel plan concisely. Do not change "
                        "prices, dates, constraints, or claim that indicative offers "
                        "are booked."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        return content

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        content = await self._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format="json",
            think=False,
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Ollama returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Ollama returned JSON that is not an object")
        return cast(dict[str, object], payload)

    async def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict[str, object] | str | None = None,
        think: bool | None = None,
    ) -> str:
        request: dict[str, object] = {
            "model": self._model,
            "stream": False,
            "messages": messages,
        }
        if response_format is not None:
            request["format"] = response_format
        if think is not None:
            request["think"] = think

        timeout = httpx.Timeout(self._timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json=request,
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())

        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama returned an invalid chat response")
        typed_message = cast(dict[str, object], message)
        content = typed_message.get("content")
        if not isinstance(content, str):
            raise ValueError("Ollama returned an invalid chat response")
        return content