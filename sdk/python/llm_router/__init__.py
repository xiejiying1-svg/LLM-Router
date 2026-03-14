"""
LLM Router Python SDK
"""
import os
from typing import Optional, Any, Iterator
import requests


class LLMRouterError(Exception):
    """Base exception for LLMRouter"""
    pass


class RateLimitError(LLMRouterError):
    """Rate limit exceeded"""
    pass


class BadGatewayError(LLMRouterError):
    """All endpoints failed"""
    pass


class AuthenticationError(LLMRouterError):
    """Authentication failed"""
    pass


class LLMRouter:
    """LLM Router Python SDK"""

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        timeout: int = 60,
        max_retries: int = 3,
        headers: dict = None
    ):
        self.base_url = base_url or os.environ.get("LLM_ROUTER_URL", "http://localhost:8000")
        self.api_key = api_key or os.environ.get("LLM_ROUTER_KEY")
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = headers or {}

        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make HTTP request"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", {}).update(self.headers)

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            elif response.status_code == 502:
                raise BadGatewayError("All endpoints failed")
            elif response.status_code == 401:
                raise AuthenticationError("Authentication failed")
            raise LLMRouterError(str(e))
        except requests.exceptions.RequestException as e:
            raise LLMRouterError(str(e))

    def chat(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tenant_id: str = None,
        **kwargs
    ) -> dict:
        """Send chat completion request"""
        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tenant_id:
            payload["tenant_id"] = tenant_id
        payload.update(kwargs)

        return self._request("POST", "/v1/chat/completions", json=payload)

    def chat_stream(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        """Send streaming chat completion request"""
        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        url = f"{self.base_url}/v1/chat/completions"
        headers = self.headers.copy()
        headers["Accept"] = "text/event-stream"

        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=self.timeout)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    yield line + "\n"

    def batch(self, requests: list[dict]) -> dict:
        """Send batch requests"""
        payload = {"requests": requests}
        return self._request("POST", "/v1/batch", json=payload)

    def get_stats(self) -> dict:
        """Get router statistics"""
        return self._request("GET", "/stats")

    def get_health(self) -> dict:
        """Check router health"""
        return self._request("GET", "/health")

    def clear_cache(self) -> dict:
        """Clear request cache"""
        return self._request("POST", "/cache/clear")

    def reload_config(self) -> dict:
        """Hot reload configuration"""
        return self._request("POST", "/config/reload")


class AsyncLLMRouter:
    """Async LLM Router Python SDK"""

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        timeout: int = 60,
        headers: dict = None
    ):
        import httpx
        self.base_url = base_url or os.environ.get("LLM_ROUTER_URL", "http://localhost:8000")
        self.api_key = api_key or os.environ.get("LLM_ROUTER_KEY")
        self.timeout = timeout
        self.headers = headers or {}

        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> dict:
        """Send chat completion request"""
        import httpx

        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()


# For convenience
__all__ = ["LLMRouter", "AsyncLLMRouter", "LLMRouterError", "RateLimitError", "BadGatewayError", "AuthenticationError"]
