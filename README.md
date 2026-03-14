# LLM Router Advanced 🧭

Multi-Provider LLM Routing with Caching, Smart Routing, Cost Optimization, Multi-Tenant & Monitoring

[English](./README.md) | [中文](./README_CN.md)

## Features

### Core
- 🔄 **Load Balancing**: Round Robin, Random, Least Connections, Weighted, Cost Optimized, Smart
- 🔁 **Retry & Failover**: Automatic retry with exponential backoff
- 🚀 **Multi-Provider**: OpenAI, Anthropic Claude, Google Gemini, Custom

### Advanced
- 📦 **Caching**: LRU/TTL cache with Redis support
- 🧠 **Smart Routing**: Auto-select model based on content (code, creative, reasoning)
- 💰 **Cost Optimization**: Auto-select cheapest suitable model
- 👥 **Multi-Tenant**: Per-tenant rate limits and budgets
- 📊 **Prometheus Metrics**: `/metrics` endpoint for monitoring
- 🔄 **Hot Reload**: Config changes without restart

### APIs
- 🔌 **Streaming**: Server-Sent Events support
- 🔌 **WebSocket**: Persistent connections
- 🔐 **API Keys**: Client authentication
- 📈 **Stats & Logs**: Request monitoring

### Developer Experience
- 🐳 **Docker**: Production-ready deployment
- 📦 **SDK**: Python & JavaScript/TypeScript
- 💻 **CLI**: Command-line management
- 📊 **Dashboard**: Web UI for monitoring

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your endpoints
```

### Run

```bash
python main.py
```

Server runs at `http://localhost:8000`

## Configuration

```yaml
load_balancer: smart
cache_enabled: true
redis_url: redis://localhost:6379
smart_routing: true
cost_optimization: true
multi_tenant: true
rate_limit: 100

endpoints:
  - name: openai-gpt4
    provider: openai
    base_url: ${OPENAI_BASE_URL}
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    cost_per_1k_tokens: 0.03
    capabilities: [reasoning, creative]
    enabled: true
```

## API Usage

### Chat Completions

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7
  }'
```

### Streaming

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Count to 5"}],
    "stream": true
  }'
```

### Batch

```bash
curl -X POST http://localhost:8000/v1/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"messages": [{"role": "user", "content": "Hello"}]},
      {"messages": [{"role": "user", "content": "Hi"}]}
    ]
  }'
```

## SDK Usage

### Python

```python
from llm_router import LLMRouter

router = LLMRouter(base_url="http://localhost:8000", api_key="YOUR_KEY")
response = router.chat(messages=[{"role": "user", "content": "Hello!"}])
print(response["choices"][0]["message"]["content"])
```

### JavaScript

```javascript
import { LLMRouter } from 'llm-router';

const router = new LLMRouter({ baseUrl: 'http://localhost:8000', apiKey: 'YOUR_KEY' });
const response = await router.chat({ messages: [{ role: 'user', content: 'Hello!' }] });
console.log(response.choices[0].message.content);
```

### CLI

```bash
# Send chat message
router-cli chat "Hello!"

# Get stats
router-cli stats

# Check health
router-cli health

# Batch requests
router-cli batch "Hello" "How are you?"
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Root info |
| `GET /health` | Health check |
| `GET /stats` | Statistics |
| `GET /metrics` | Prometheus metrics |
| `POST /cache/clear` | Clear cache |
| `POST /config/reload` | Hot reload config |
| `POST /chat/completions` | Chat API |
| `POST /v1/chat/completions` | OpenAI-compatible |
| `POST /v1/batch` | Batch requests |

## Docker

```bash
docker build -t llm-router .
docker run -p 8000:8000 -v config.yaml:/app/config.yaml llm-router
```

## Dashboard

Open `dashboard/index.html` in browser or serve it:

```bash
cd dashboard && python -m http.server 8080
```

Then visit `http://localhost:8080`

## Documentation

- [API Docs](http://localhost:8000/docs) - Swagger UI
- [Deployment Guide](./DEPLOYMENT.md)
- [FAQ](./FAQ.md)
- [Benchmark](./BENCHMARK.md)

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       v
┌─────────────────────────────────────────┐
│           LLM Router                     │
├─────────────────────────────────────────┤
│  ┌─────────┐  ┌──────────┐  ┌────────┐  │
│  │ Cache   │  │ Smart    │  │ Cost   │  │
│  │ (LRU/   │  │ Router   │  │ Optim  │  │
│  │ Redis)  │  │          │  │        │  │
│  └────┬────┘  └────┬─────┘  └───┬────┘  │
│       │            │            │        │
│  ┌────┴────────────┴────────────┴────┐  │
│  │         Load Balancer              │  │
│  │  (round_robin/random/weighted)    │  │
│  └────────────────┬───────────────────┘  │
│                   │                        │
│       ┌───────────┼───────────┐           │
│       v           v           v           │
│  ┌────────┐  ┌────────┐  ┌────────┐      │
│  │Endpoint│  │Endpoint│  │Endpoint│      │
│  │   A    │  │   B    │  │   C    │      │
│  └────────┘  └────────┘  └────────┘      │
└─────────────────────────────────────────┘
```

## License

MIT
