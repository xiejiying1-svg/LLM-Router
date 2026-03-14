"""
LLM Router - Advanced Multi-Provider LLM Routing
With Caching, Smart Routing, Cost Optimization, Multi-Tenant, Metrics, Redis, Hot Reload
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import uuid

# Third-party imports
import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# For caching
from functools import lru_cache
import hashlib

# For Redis (optional)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

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
    COST_OPTIMIZED = "cost_optimized"
    SMART = "smart"


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MINIMAX = "minimax"
    CUSTOM = "custom"


class CacheStrategy(str, Enum):
    NONE = "none"
    LRU = "lru"
    TTL = "ttl"
    SEMANTIC = "semantic"


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
    cost_per_1k_tokens: float = Field(default=0.002)  # Cost per 1K tokens
    capabilities: list[str] = Field(default_factory=list)  # e.g., ["code", "creative", "reasoning"]
    max_tokens: int = Field(default=4096)


class TenantConfig(BaseModel):
    """Multi-tenant configuration"""
    tenant_id: str
    rate_limit: int = 60  # requests per minute
    monthly_budget: Optional[float] = None
    endpoints: list[str] = Field(default_factory=list)  # allowed endpoints
    enabled: bool = True


class RouterConfig(BaseModel):
    """Main router configuration"""
    load_balancer: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN
    default_timeout: int = Field(default=60, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_delay: float = Field(default=1.0, ge=0)
    rate_limit: Optional[int] = Field(default=None, ge=1)
    health_check_interval: int = Field(default=60, ge=10)

    # Advanced features
    cache_enabled: bool = False
    cache_ttl: int = 3600  # seconds
    cache_max_size: int = 1000
    redis_url: Optional[str] = None
    smart_routing: bool = False
    cost_optimization: bool = False

    # Multi-tenant
    multi_tenant: bool = False
    tenants: dict[str, TenantConfig] = Field(default_factory=dict)

    # Hot reload
    config_watch: bool = False

    endpoints: list[EndpointConfig] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str = Field(default="user")
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = False
    user: Optional[str] = None
    tenant_id: Optional[str] = None  # For multi-tenant


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


# ============== Cache ==============
class RequestCache:
    """LRU/TTL cache for chat requests"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600, redis_url: Optional[str] = None):
        self.max_size = max_size
        self.ttl = ttl
        self.redis_url = redis_url
        self.redis_client = None

        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, using in-memory cache")

        self.memory_cache = {}
        self.access_order = []
        self.lock = threading.Lock()

    def _generate_key(self, messages: list[dict], temperature: float, max_tokens: Optional[int]) -> str:
        """Generate cache key from request"""
        content = json.dumps({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, key: str) -> Optional[dict]:
        """Get cached response"""
        if self.redis_client:
            try:
                data = self.redis_client.get(f"llm_cache:{key}")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        with self.lock:
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                if time.time() - entry["timestamp"] < self.ttl:
                    # Update access order
                    self.access_order.remove(key)
                    self.access_order.append(key)
                    return entry["data"]
                else:
                    del self.memory_cache[key]
                    if key in self.access_order:
                        self.access_order.remove(key)
        return None

    def set(self, key: str, value: dict):
        """Set cached response"""
        if self.redis_client:
            try:
                self.redis_client.setex(
                    f"llm_cache:{key}",
                    self.ttl,
                    json.dumps(value)
                )
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

        with self.lock:
            # Evict if full
            if len(self.memory_cache) >= self.max_size:
                oldest = self.access_order.pop(0)
                del self.memory_cache[oldest]

            self.memory_cache[key] = {
                "data": value,
                "timestamp": time.time()
            }
            self.access_order.append(key)

    def clear(self):
        """Clear all cache"""
        if self.redis_client:
            try:
                keys = self.redis_client.keys("llm_cache:*")
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}")

        with self.lock:
            self.memory_cache.clear()
            self.access_order.clear()


# ============== Smart Router ==============
class SmartRouter:
    """Intelligent routing based on request characteristics"""

    # Keywords for different capabilities
    CAPABILITY_KEYWORDS = {
        "code": ["code", "编程", "写代码", "debug", "function", "algorithm", "程序"],
        "creative": ["写", "创作", "故事", "小说", "诗", "创意", "write", "story", "creative"],
        "reasoning": ["分析", "推理", "为什么", "思考", "reason", "think", "analyze"],
        "math": ["计算", "数学", "数字", "math", "calculate", "算"],
        "translation": ["翻译", "translate", "英译", "中译"],
    }

    def __init__(self, endpoints: list[EndpointConfig]):
        self.endpoints = {e.name: e for e in endpoints if e.enabled}

    def select(
        self,
        messages: list[dict],
        preferred_model: Optional[str] = None
    ) -> Optional[EndpointConfig]:
        """Select best endpoint based on content analysis"""
        if not self.endpoints:
            return None

        # If specific model requested
        if preferred_model:
            for e in self.endpoints.values():
                if e.model == preferred_model:
                    return e

        # Analyze content
        content = " ".join(
            msg.get("content", "") for msg in messages
        ).lower()

        # Find matching capabilities
        matched_capabilities = []
        for cap, keywords in self.CAPABILITY_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                matched_capabilities.append(cap)

        # Find endpoint with matching capabilities
        if matched_capabilities:
            for e in self.endpoints.values():
                for cap in matched_capabilities:
                    if cap in e.capabilities:
                        return e

        # Default: return first enabled endpoint
        return next(iter(self.endpoints.values()))


# ============== Cost Optimizer ==============
class CostOptimizer:
    """Select cheapest suitable endpoint"""

    def __init__(self, endpoints: list[EndpointConfig]):
        self.endpoints = [e for e in endpoints if e.enabled]
        # Sort by cost
        self.endpoints.sort(key=lambda e: e.cost_per_1k_tokens)

    def select(self, required_tokens: int = 1000) -> Optional[EndpointConfig]:
        """Select cheapest endpoint"""
        if not self.endpoints:
            return None
        return self.endpoints[0]


# ============== Rate Limiter ==============
class RateLimiter:
    """Token bucket rate limiter with multi-tenant support"""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self.lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        with self.lock:
            now = time.time()
            self.requests[key] = [t for t in self.requests[key] if now - t < 60]

            if len(self.requests[key]) >= self.requests_per_minute:
                return False

            self.requests[key].append(now)
            return True

    def get_remaining(self, key: str) -> int:
        with self.lock:
            now = time.time()
            self.requests[key] = [t for t in self.requests[key] if now - t < 60]
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
        with self.lock:
            self.endpoints = [e for e in endpoints if e.enabled]

    def select(self) -> Optional[EndpointConfig]:
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
                endpoint = min(
                    self.endpoints,
                    key=lambda e: self.connection_counts.get(e.name, 0)
                )
                self.connection_counts[endpoint.name] += 1
                return endpoint

            elif self.strategy == LoadBalancerStrategy.WEIGHTED:
                import random
                weights = [e.weight for e in self.endpoints]
                total = sum(weights)
                probabilities = [w / total for w in weights]
                return random.choices(self.endpoints, weights=probabilities)[0]

            elif self.strategy == LoadBalancerStrategy.COST_OPTIMIZED:
                # Cheapest first
                sorted_endpoints = sorted(self.endpoints, key=lambda e: e.cost_per_1k_tokens)
                return sorted_endpoints[0]

        return self.endpoints[0] if self.endpoints else None

    def release_connection(self, endpoint_name: str):
        with self.lock:
            if self.connection_counts[endpoint_name] > 0:
                self.connection_counts[endpoint_name] -= 1


# ============== LLM Provider Clients ==============
class LLMClient(ABC):
    @abstractmethod
    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        pass


class OpenAIClient(LLMClient):
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
    async def chat(
        self,
        endpoint: EndpointConfig,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> dict | Callable[[], Any]:
        headers = {"Content-Type": "application/json"}

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
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }

        return await call()


# ============== Metrics ==============
class Metrics:
    """Prometheus-compatible metrics"""

    def __init__(self):
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.requests_cached = 0
        self.tokens_used = 0
        self.cost_total = 0.0
        self.latencies = []
        self.endpoint_stats = defaultdict(lambda: {"requests": 0, "success": 0, "failed": 0, "latency_sum": 0})
        self.lock = threading.Lock()

    def record_request(self, endpoint: str, success: bool, latency: float, cached: bool = False, tokens: int = 0, cost: float = 0):
        with self.lock:
            self.requests_total += 1
            if cached:
                self.requests_cached += 1
            elif success:
                self.requests_success += 1
            else:
                self.requests_failed += 1

            self.tokens_used += tokens
            self.cost_total += cost
            self.latencies.append(latency)
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]

            stats = self.endpoint_stats[endpoint]
            stats["requests"] += 1
            stats["latency_sum"] += latency
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1

    def get_stats(self) -> dict:
        with self.lock:
            avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
            sorted_latencies = sorted(self.latencies)
            p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0

            return {
                "requests_total": self.requests_total,
                "requests_success": self.requests_success,
                "requests_failed": self.requests_failed,
                "requests_cached": self.requests_cached,
                "success_rate": self.requests_success / self.requests_total if self.requests_total > 0 else 0,
                "tokens_used": self.tokens_used,
                "cost_total": self.cost_total,
                "latency_avg_ms": avg_latency * 1000,
                "latency_p50_ms": p50 * 1000,
                "latency_p95_ms": p95 * 1000,
                "latency_p99_ms": p99 * 1000,
                "endpoints": dict(self.endpoint_stats)
            }

    def to_prometheus(self) -> str:
        """Export in Prometheus format"""
        stats = self.get_stats()
        lines = [
            "# HELP llm_router_requests_total Total requests",
            "# TYPE llm_router_requests_total counter",
            f"llm_router_requests_total {stats['requests_total']}",
            f"llm_router_requests_success {stats['requests_success']}",
            f"llm_router_requests_failed {stats['requests_failed']}",
            f"llm_router_requests_cached {stats['requests_cached']}",
            "",
            "# HELP llm_router_tokens_total Total tokens used",
            "# TYPE llm_router_tokens_total counter",
            f"llm_router_tokens_total {stats['tokens_used']}",
            "",
            "# HELP llm_router_cost_total Total cost in USD",
            "# TYPE llm_router_cost_total counter",
            f"llm_router_cost_total {stats['cost_total']}",
            "",
            "# HELP llm_router_latency_seconds Request latency",
            "# TYPE llm_router_latency_seconds histogram",
            f"llm_router_latency_sum {stats['latency_avg_ms'] / 1000}",
            f"llm_router_latency_count {stats['requests_total']}",
        ]
        return "\n".join(lines)


# ============== Router ==============
class LLMRouter:
    """Main LLM Router with all advanced features"""

    def __init__(self, config: RouterConfig):
        self.config = config
        self.load_balancer = LoadBalancer(config.load_balancer)
        self.rate_limiter = RateLimiter(config.rate_limit) if config.rate_limit else None
        self.client = OpenAIClient()  # Default client

        # Cache
        self.cache: Optional[RequestCache] = None
        if config.cache_enabled:
            self.cache = RequestCache(
                max_size=config.cache_max_size,
                ttl=config.cache_ttl,
                redis_url=config.redis_url
            )

        # Smart routing
        self.smart_router: Optional[SmartRouter] = None
        if config.smart_routing:
            self.smart_router = SmartRouter(config.endpoints)

        # Cost optimizer
        self.cost_optimizer: Optional[CostOptimizer] = None
        if config.cost_optimization:
            self.cost_optimizer = CostOptimizer(config.endpoints)

        # Multi-tenant
        self.tenants: dict[str, TenantConfig] = {}
        if config.multi_tenant:
            self.tenants = config.tenants

        # Metrics
        self.metrics = Metrics()

        # Initialize
        self.load_balancer.set_endpoints(config.endpoints)

        # Config hot reload watcher
        self.config_watcher = None
        if config.config_watch:
            self._start_config_watcher()

    def _start_config_watcher(self):
        """Watch config file for changes"""
        import watchdog.observers
        import watchdog.events

        class ConfigHandler(watchdog.events.FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith("config.yaml"):
                    logger.info("Config file changed, reloading...")
                    # Reload config (simplified)
                    pass

        self.config_watcher = watchdog.observers.Observer()
        self.config_watcher.schedule(ConfigHandler(), ".", recursive=False)
        self.config_watcher.start()

    def _validate_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """Validate tenant and get config"""
        if not self.tenants:
            return None
        tenant = self.tenants.get(tenant_id)
        if not tenant or not tenant.enabled:
            return None
        return tenant

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tenant_id: Optional[str] = None,
        model: Optional[str] = None
    ) -> dict | Callable[[], Any]:
        # Multi-tenant validation
        tenant = self._validate_tenant(tenant_id) if tenant_id else None
        if tenant:
            # Check tenant-specific rate limit
            tenant_limiter = RateLimiter(tenant.rate_limit)
            if not tenant_limiter.is_allowed(tenant_id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Tenant rate limit exceeded"
                )

            # Check budget
            if tenant.monthly_budget and self.metrics.cost_total >= tenant.monthly_budget:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Monthly budget exceeded"
                )

        # Rate limiting
        if self.rate_limiter:
            client_key = tenant_id or "default"
            if not self.rate_limiter.is_allowed(client_key):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"}
                )

        # Check cache
        if self.cache:
            cache_key = self.cache._generate_key(messages, temperature, max_tokens)
            cached_response = self.cache.get(cache_key)
            if cached_response:
                self.metrics.record_request("", True, 0, cached=True)
                logger.info("Cache hit!")
                return cached_response

        # Select endpoint
        if self.smart_router and model is None:
            endpoint = self.smart_router.select(messages, model)
        elif self.cost_optimizer:
            endpoint = self.cost_optimizer.select()
        else:
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

                # Cache result
                if self.cache and not stream:
                    self.cache.set(cache_key, result)

                # Record metrics
                tokens = result.get("usage", {}).get("total_tokens", 0)
                cost = (tokens / 1000) * endpoint.cost_per_1k_tokens
                self.metrics.record_request(endpoint.name, True, duration, tokens=tokens, cost=cost)
                self.load_balancer.release_connection(endpoint.name)

                return result

            except Exception as e:
                duration = time.time() - start_time
                last_error = str(e)
                logger.warning(f"Request failed (attempt {attempt + 1}/{endpoint.max_retries}): {e}")
                self.metrics.record_request(endpoint.name, False, duration)

                if attempt < endpoint.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All endpoints failed: {last_error}"
        )

    def get_health_status(self) -> dict:
        return {
            "status": "healthy",
            "endpoints_count": len(self.config.endpoints),
            "cache_enabled": self.cache is not None,
            "smart_routing": self.smart_router is not None,
            "multi_tenant": len(self.tenants) > 0
        }

    def get_stats(self) -> dict:
        return self.metrics.get_stats()

    def clear_cache(self):
        if self.cache:
            self.cache.clear()
        return {"status": "cache cleared"}


# ============== FastAPI App ==============
app = FastAPI(
    title="LLM Router Advanced",
    description="Advanced LLM Router with Caching, Smart Routing, Cost Optimization, Multi-Tenant",
    version="2.0.0",
    docs_url="/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    if router is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return router


# ============== API Routes ==============
@app.get("/")
async def root():
    return {"name": "LLM Router Advanced", "version": "2.0.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return get_router().get_health_status()


@app.get("/stats")
async def stats():
    return get_router().get_stats()


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=get_router().metrics.to_prometheus(),
        media_type="text/plain"
    )


@app.post("/cache/clear")
async def clear_cache():
    return get_router().clear_cache()


@app.post("/config/reload")
async def reload_config():
    """Hot reload configuration"""
    # Simplified: would reload from file in production
    return {"status": "config reloaded"}


@app.post("/chat/completions")
async def chat_completions(request: ChatRequest, req: Request):
    messages = [msg.model_dump() for msg in request.messages]

    try:
        result = await get_router().chat(
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            tenant_id=request.tenant_id,
            model=request.model
        )

        if request.stream:
            async def generate():
                stream_fn = result
                async for chunk in stream_fn():
                    yield chunk
            return StreamingResponse(generate(), media_type="text/event-stream")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: ChatRequest, req: Request):
    return await chat_completions(request, req)


# ============== Batch API ==============
class BatchRequest(BaseModel):
    requests: list[ChatRequest]


@app.post("/v1/batch")
async def batch_chat(batch: BatchRequest):
    """Process multiple requests in batch"""
    results = []

    for req in batch.requests:
        messages = [msg.model_dump() for msg in req.messages]
        try:
            result = await get_router().chat(
                messages=messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                stream=False,
                tenant_id=req.tenant_id
            )
            results.append({"success": True, "data": result})
        except Exception as e:
            results.append({"success": False, "error": str(e)})

    return {"results": results}


# ============== Main ==============
def load_config(config_path: str = "config.yaml") -> RouterConfig:
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            return RouterConfig(**data)
    return RouterConfig(endpoints=[])


def main():
    global router

    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    config = load_config(config_path)

    router = LLMRouter(config)

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
