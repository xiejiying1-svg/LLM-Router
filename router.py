"""
LLM Router - Multi-Provider LLM Routing with Load Balancing, Retry, and Rate Limiting
"""
import asyncio
import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from collections import defaultdict
import threading

# Third-party imports
import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== Enums ==============
class LoadBalancerStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MINIMAX = "minimax"
    CUSTOM = "custom"


# ============== Data Models ==============
class EndpointConfig(BaseModel):
    """Configuration for a single LLM endpoint"""
    name: str
    provider: ModelProvider
    base_url: str
    api_key: str
    model: str
    weight: int = Field(default=1, ge=1)
    timeout: int = Field(default=60, ge=1)
    max_retries: int = Field(default=3, ge=0)
    enabled: bool = True


class RouterConfig(BaseModel):
    """Main router configuration"""
    load_balancer: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN
    default_timeout: int = Field(default=60, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_delay: float = Field(default=1.0, ge=0)
    rate_limit: Optional[int] = Field(default=None, ge=1)  # requests per minute
    health_check_interval: int = Field(default=60, ge=10)  # seconds
    endpoints: list[EndpointConfig] = Field(default_factory=list)


class ChatMessage(BaseModel):
    """Chat message format"""
    role: str = Field(default="user")
    content: str


class ChatRequest(BaseModel):
    """Chat completion request"""
    model: Optional[str] = None
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = False
    user: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat completion response"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


class APIKeyInfo(BaseModel):
    """API Key information"""
    key_hash: str
    prefix: str
    created_at: int
    rate_limit: Optional[int] = None
    enabled: bool = True


# ============== Rate Limiter ==============
class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self.lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed"""
        with self.lock:
            now = time.time()
            # Clean old requests
            self.requests[key] = [
                t for t in self.requests[key]
                if now - t < 60
            ]

            if len(self.requests[key]) >= self.requests_per_minute:
                return False

            self.requests[key].append(now)
            return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests"""
        with self.lock:
            now = time.time()
            self.requests[key] = [
                t for t in self.requests[key]
                if now - t < 60
            ]
            return max(0, self.requests_per_minute - len(self.requests[key]))


# ============== Load Balancer ==============
class LoadBalancer:
    """Load balancer with multiple strategies"""

    def __init__(self, strategy: LoadBalancerStrategy):
        self.strategy = strategy
        self.endpoints: list[EndpointConfig] = []
        self.connection_counts = defaultdict(int)
        self.round_robin_index = 0
        self.lock = threading.Lock()

    def set_endpoints(self, endpoints: list[EndpointConfig]):
        """Set available endpoints"""
        with self.lock:
            self.endpoints = [e for e in endpoints if e.enabled]
            # Reset connection counts for new endpoints
            self.connection_counts = defaultdict(int)

    def select(self) -> Optional[EndpointConfig]:
        """Select an endpoint based on strategy"""
        if not self.endpoints:
            return None

        with self.lock:
            if self.strategy == LoadBalancerStrategy.ROUND_ROBIN:
                endpoint = self.endpoints[self.round_robin_index]
                self.round_robin_index = (self.round_robin_index + 1) % len(self.endpoints)
                return endpoint

            elif self.strategy == LoadBalancerStrategy.RANDOM:
                import random
                return random.choice(self.endpoints)

            elif self.strategy == LoadBalancerStrategy.LEAST_CONNECTIONS:
                # Select endpoint with least connections
                endpoint = min(
                    self.endpoints,
                    key=lambda e: self.connection_counts.get(e.name, 0)
                )
                self.connection_counts[endpoint.name] += 1
                return endpoint

            elif self.strategy == LoadBalancerStrategy.WEIGHTED:
                # Weighted random selection
                import random
                weights = [e.weight for e in self.endpoints]
                total = sum(weights)
                probabilities = [w / total for w in weights]
                return random.choices(self.endpoints, weights=probabilities)[0]

        return self.endpoints[0]

    def release_connection(self, endpoint_name: str):
        """Release a connection (for least_connections)"""
        with self.lock:
            if self.connection_counts[endpoint_name] > 0:
                self.connection_counts[endpoint_name] -= 1


# ============== LLM Provider Clients ==============
class LLMClient(ABC):
    """Abstract LLM client"""

    @abstractmethod
    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        """Send chat request"""
        pass


class OpenAIClient(LLMClient):
    """OpenAI-compatible client"""

    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        headers = {
            "Authorization": f"Bearer {endpoint.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": endpoint.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async def call():
            async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                response = await client.post(
                    f"{endpoint.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()

        if stream:
            async def stream_call():
                async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{endpoint.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    ) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                yield line + "\n\n"
            return stream_call

        return await call()


class AnthropicClient(LLMClient):
    """Anthropic Claude client"""

    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        headers = {
            "x-api-key": endpoint.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        # Convert messages to Anthropic format
        system_message = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append(msg)

        payload = {
            "model": endpoint.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
            "stream": stream
        }
        if system_message:
            payload["system"] = system_message

        async def call():
            async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                response = await client.post(
                    f"{endpoint.base_url}/messages",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                # Convert to OpenAI format
                return {
                    "id": f"chatcmpl-{data.get('id', '')}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": endpoint.model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": data.get("content", [{}])[0].get("text", "")
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                        "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
                    }
                }

        if stream:
            async def stream_call():
                async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{endpoint.base_url}/messages",
                        headers=headers,
                        json=payload
                    ) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                yield line + "\n\n"
            return stream_call

        return await call()


class GeminiClient(LLMClient):
    """Google Gemini client"""

    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        headers = {
            "Content-Type": "application/json"
        }

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "stream": stream
            }
        }

        async def call():
            async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                response = await client.post(
                    f"{endpoint.base_url}/{endpoint.model}:generateContent",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                # Convert to OpenAI format
                return {
                    "id": f"chatcmpl-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": endpoint.model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }

        if stream:
            async def stream_call():
                async with httpx.AsyncClient(timeout=endpoint.timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{endpoint.base_url}/{endpoint.model}:streamGenerateContent",
                        headers=headers,
                        json=payload
                    ) as response:
                        async for line in response.aiter_lines():
                            if line:
                                yield line + "\n\n"
            return stream_call

        return await call()


# ============== Router ==============
class LLMRouter:
    """Main LLM Router"""

    def __init__(self, config: RouterConfig):
        self.config = config
        self.load_balancer = LoadBalancer(config.load_balancer)
        self.rate_limiter = RateLimiter(config.rate_limit) if config.rate_limit else None
        self.client = self._create_client()
        self.api_keys: dict[str, APIKeyInfo] = {}
        self.health_status: dict[str, bool] = {}
        self.request_logs: list[dict] = []
        self.lock = threading.Lock()

        # Initialize endpoints
        self.load_balancer.set_endpoints(config.endpoints)
        for endpoint in config.endpoints:
            self.health_status[endpoint.name] = True

    def _create_client(self) -> LLMClient:
        """Create appropriate client based on config"""
        # For now, default to OpenAI-compatible
        return OpenAIClient()

    def register_api_key(self, api_key: str, rate_limit: Optional[int] = None) -> str:
        """Register an API key and return its hash"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        prefix = api_key[:8] if len(api_key) >= 8 else api_key

        with self.lock:
            self.api_keys[key_hash] = APIKeyInfo(
                key_hash=key_hash,
                prefix=prefix,
                created_at=int(time.time()),
                rate_limit=rate_limit,
                enabled=True
            )

        return key_hash

    def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key"""
        if not self.api_keys:
            return True  # No keys registered, allow all

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_info = self.api_keys.get(key_hash)

        if not key_info or not key_info.enabled:
            return False

        # Check rate limit if set
        if key_info.rate_limit:
            limiter = RateLimiter(key_info.rate_limit)
            return limiter.is_allowed(key_hash)

        return True

    def get_api_key_remaining(self, api_key: str) -> int:
        """Get remaining requests for API key"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_info = self.api_keys.get(key_hash)

        if not key_info or not key_info.rate_limit:
            return -1

        limiter = RateLimiter(key_info.rate_limit)
        return limiter.get_remaining(key_hash)

    def _log_request(self, endpoint: str, success: bool, duration: float, error: Optional[str] = None):
        """Log a request"""
        with self.lock:
            self.request_logs.append({
                "timestamp": time.time(),
                "endpoint": endpoint,
                "success": success,
                "duration": duration,
                "error": error
            })
            # Keep only last 1000 logs
            if len(self.request_logs) > 1000:
                self.request_logs = self.request_logs[-1000:]

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        api_key: Optional[str] = None
    ) -> dict | Callable[[], Any]:
        """Send chat request with retry and fallback"""
        # Validate API key
        if api_key and not self.validate_api_key(api_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded or invalid API key"
            )

        # Rate limiting
        if self.rate_limiter:
            client_key = api_key or "default"
            if not self.rate_limiter.is_allowed(client_key):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"}
                )

        # Select endpoint
        endpoint = self.load_balancer.select()
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available endpoints"
            )

        # Retry logic
        last_error = None
        for attempt in range(endpoint.max_retries):
            start_time = time.time()
            try:
                result = await self.client.chat(
                    endpoint=endpoint,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream
                )

                duration = time.time() - start_time
                self._log_request(endpoint.name, True, duration)
                self.load_balancer.release_connection(endpoint.name)

                return result

            except Exception as e:
                duration = time.time() - start_time
                last_error = str(e)
                logger.warning(f"Request failed (attempt {attempt + 1}/{endpoint.max_retries}): {e}")
                self._log_request(endpoint.name, False, duration, str(e))

                # Wait before retry
                if attempt < endpoint.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        # All retries failed
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All endpoints failed: {last_error}"
        )

    def get_health_status(self) -> dict:
        """Get health status of all endpoints"""
        return {
            "endpoints": {
                name: status for name, status in self.health_status.items()
            },
            "total_endpoints": len(self.health_status),
            "healthy_endpoints": sum(self.health_status.values())
        }

    def get_stats(self) -> dict:
        """Get router statistics"""
        with self.lock:
            total_requests = len(self.request_logs)
            successful = sum(1 for log in self.request_logs if log["success"])
            failed = total_requests - successful

            avg_duration = 0
            if self.request_logs:
                avg_duration = sum(log["duration"] for log in self.request_logs) / total_requests

            # Per-endpoint stats
            endpoint_stats = defaultdict(lambda: {"requests": 0, "success": 0, "failed": 0})
            for log in self.request_logs:
                endpoint_stats[log["endpoint"]]["requests"] += 1
                if log["success"]:
                    endpoint_stats[log["endpoint"]]["success"] += 1
                else:
                    endpoint_stats[log["endpoint"]]["failed"] += 1

            return {
                "total_requests": total_requests,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / total_requests if total_requests > 0 else 0,
                "average_duration": avg_duration,
                "endpoints": dict(endpoint_stats)
            }

    def get_logs(self, limit: int = 100) -> list[dict]:
        """Get recent request logs"""
        with self.lock:
            return self.request_logs[-limit:]


# ============== FastAPI App ==============
app = FastAPI(
    title="LLM Router",
    description="Multi-Provider LLM Routing with Load Balancing, Retry, and Rate Limiting",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global router instance
router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get router instance"""
    if router is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Router not initialized"
        )
    return router


# ============== API Routes ==============
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "LLM Router",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return get_router().get_health_status()


@app.get("/stats")
async def stats():
    """Get router statistics"""
    return get_router().get_stats()


@app.get("/logs")
async def logs(limit: int = 100):
    """Get request logs"""
    return get_router().get_logs(limit)


@app.post("/keys")
async def create_api_key(rate_limit: Optional[int] = None):
    """Create a new API key"""
    import secrets
    api_key = f"sk-{secrets.token_urlsafe(32)}"
    key_hash = get_router().register_api_key(api_key, rate_limit)
    return {
        "api_key": api_key,
        "key_hash": key_hash
    }


@app.post("/chat/completions")
async def chat_completions(request: ChatRequest, req: Request):
    """Chat completions endpoint"""
    # Get API key from header
    api_key = req.headers.get("Authorization", "").replace("Bearer ", "")

    # Convert messages to dict format
    messages = [msg.model_dump() for msg in request.messages]

    try:
        result = await get_router().chat(
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            api_key=api_key
        )

        if request.stream:
            async def generate():
                stream_fn = result
                async for chunk in stream_fn():
                    yield chunk
            return StreamingResponse(
                generate(),
                media_type="text/event-stream"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: ChatRequest, req: Request):
    """OpenAI-compatible chat completions endpoint"""
    return await chat_completions(request, req)


# ============== WebSocket Endpoint ==============
@app.websocket("/ws/chat")
async def websocket_chat(websocket):
    """WebSocket chat endpoint"""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            messages = data.get("messages", [])
            temperature = data.get("temperature", 0.7)
            max_tokens = data.get("max_tokens")
            stream = data.get("stream", False)

            result = await get_router().chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )

            if stream:
                stream_fn = result
                async for chunk in stream_fn():
                    await websocket.send_text(chunk)
            else:
                await websocket.send_json(result)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


# ============== Main ==============
def load_config(config_path: str = "config.yaml") -> RouterConfig:
    """Load configuration from YAML file"""
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            return RouterConfig(**data)
    return RouterConfig(endpoints=[])


def main():
    """Main entry point"""
    global router

    # Load config
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    config = load_config(config_path)

    # Create router
    router = LLMRouter(config)

    # Run server
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
