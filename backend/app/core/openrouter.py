import json
import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class BudgetExceededError(Exception):
    def __init__(self, model: str, budget: float, spent: float, fallback: Optional[str] = None):
        self.model = model
        self.budget = budget
        self.spent = spent
        self.fallback = fallback
        super().__init__(f"Budget exceeded for {model}: ${spent:.4f} / ${budget:.2f} per day")


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self._client: Optional[httpx.AsyncClient] = None
        self._tracker = None

    @property
    def tracker(self):
        if self._tracker is None:
            from app.learning.cost_tracker import cost_tracker
            self._tracker = cost_tracker
        return self._tracker

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://metatrader.app",
                    "X-Title": "MetaTrader",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[dict]:
        client = await self._get_client()
        response = await client.get("/models")
        response.raise_for_status()
        return response.json().get("data", [])

async def chat_completion(
    self,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    response_format: Optional[dict] = None,
    stop: Optional[list[str]] = None,
    extra_headers: Optional[dict[str, str]] = None,
) -> dict:
    client = await self._get_client()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    if stop:
        payload["stop"] = stop

    headers = {}
    if extra_headers:
        headers.update(extra_headers)

    response = await client.post("/chat/completions", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

    async def chat_completion_tracked(
        self,
        user_id: int,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format: Optional[dict] = None,
        stop: Optional[list[str]] = None,
        strategy_id: Optional[int] = None,
        node_label: Optional[str] = None,
        enforce_budget: bool = True,
        auto_fallback: bool = True,
    ) -> dict:
        if enforce_budget:
            # Estimate cost from prompt tokens
            prompt_text = "".join(m.get("content", "") for m in messages)
            estimated_tokens = max(len(prompt_text) // 4, 50)
            estimated_cost = await self.tracker.get_model_cost_estimate(model, estimated_tokens)

            check = await self.tracker.check_budget(user_id, model, estimated_cost)

            if not check.allowed:
                if auto_fallback:
                    fallback_model = await self.tracker.get_cheaper_fallback(model)
                    if fallback_model and fallback_model != model:
                        logger.warning(
                            f"Budget exceeded for {model}, falling back to {fallback_model} "
                            f"(${check.spent:.4f} / ${check.budget:.2f})"
                        )
                        model = fallback_model
                    else:
                        raise BudgetExceededError(model, check.budget, check.spent)
                else:
                    raise BudgetExceededError(model, check.budget, check.spent)

        extra_headers = {}
        try:
            from app.core.credentials import credential_service
            user_api_key = await credential_service.get_effective_key(
                user_id, "openrouter", settings.OPENROUTER_API_KEY
            )
            if user_api_key and user_api_key != self.api_key:
                extra_headers["Authorization"] = f"Bearer {user_api_key}"
        except Exception as e:
            logger.debug(f"Failed to load per-user OpenRouter key: {e}")

        response = await self.chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            stop=stop,
            extra_headers=extra_headers if extra_headers else None,
        )

        cost = self.extract_cost(response)
        tokens = self.extract_tokens(response)

        try:
            await self.tracker.log_model_call(
                user_id=user_id,
                model_name=model,
                request_tokens=tokens.get("prompt_tokens", 0),
                response_tokens=tokens.get("completion_tokens", 0),
                usd_cost=cost,
                strategy_id=strategy_id,
                model_node_label=node_label,
            )
        except Exception as e:
            logger.error(f"Failed to log model cost: {e}")

        return response

    def extract_cost(self, response: dict) -> float:
        usage = response.get("usage", {})
        return float(usage.get("cost", 0.0))

    def extract_tokens(self, response: dict) -> dict:
        usage = response.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    @staticmethod
    def extract_content(response: dict) -> str:
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return ""


openrouter_client: Optional[OpenRouterClient] = None


def get_openrouter() -> OpenRouterClient:
    global openrouter_client
    if openrouter_client is None:
        openrouter_client = OpenRouterClient()
    return openrouter_client