# LLM Router Python SDK

## Installation

```bash
pip install llm-router
```

## Quick Start

```python
from llm_router import LLMRouter

# Initialize router
router = LLMRouter(
    base_url="http://localhost:8000",
    api_key="your-api-key"  # Optional
)

# Simple chat
response = router.chat(
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response["choices"][0]["message"]["content"])

# Streaming
for chunk in router.chat_stream(
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
):
    print(chunk, end="")
```

## API Reference

### LLMRouter

```python
router = LLMRouter(
    base_url: str = "http://localhost:8000",
    api_key: str = None,
    timeout: int = 60,
    max_retries: int = 3
)
```

#### Methods

##### chat()

Send a chat completion request.

```python
response = router.chat(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    stream: bool = False,
    tenant_id: str = None
)
```

##### chat_stream()

Send a streaming chat request.

```python
for chunk in router.chat_stream(messages=[...]):
    print(chunk)
```

##### batch()

Send multiple requests in batch.

```python
requests = [
    {"messages": [{"role": "user", "content": "Hello"}]},
    {"messages": [{"role": "user", "content": "Hi"}]}
]
results = router.batch(requests)
```

##### get_stats()

Get router statistics.

```python
stats = router.get_stats()
print(stats["requests_total"])
```

##### get_health()

Check router health.

```python
health = router.get_health()
print(health["status"])
```

## Advanced Usage

### Custom Headers

```python
router = LLMRouter(
    base_url="http://localhost:8000",
    headers={"X-Custom-Header": "value"}
)
```

### Error Handling

```python
from llm_router.exceptions import (
    RateLimitError,
    BadGatewayError,
    AuthenticationError
)

try:
    response = router.chat(messages=[...])
except RateLimitError:
    print("Rate limited!")
except BadGatewayError:
    print("All endpoints failed!")
except AuthenticationError:
    print("Auth failed!")
```

### Async Usage

```python
import asyncio
from llm_router import AsyncLLMRouter

async def main():
    router = AsyncLLMRouter(base_url="http://localhost:8000")
    response = await router.chat(messages=[...])
    print(response)

asyncio.run(main())
```

## Configuration

### Environment Variables

```bash
export LLM_ROUTER_URL="http://localhost:8000"
export LLM_ROUTER_KEY="your-api-key"
```

## Examples

See `examples/` directory for more examples.
