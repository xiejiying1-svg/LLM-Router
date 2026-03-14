# LLM Router 🧭

Multi-Provider LLM Routing with Load Balancing, Retry, Rate Limiting & Monitoring

[English](./README.md) | [中文](./README_CN.md)

## Features

- 🔄 **Load Balancing**: Round Robin, Random, Least Connections, Weighted
- 🔁 **Retry & Failover**: Automatic retry with exponential backoff
- 🚀 **Multi-Provider**: OpenAI, Anthropic Claude, Google Gemini
- 📊 **Rate Limiting**: Per-client and global rate limiting
- 🔌 **Streaming**: Server-Sent Events support
- 🔌 **WebSocket**: Persistent connections for chat
- 🔐 **API Keys**: Manage client authentication
- 📈 **Monitoring**: Health checks, stats, request logs
- 🐳 **Docker**: Ready for production deployment

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
load_balancer: round_robin
default_timeout: 60
max_retries: 3
retry_delay: 1.0
rate_limit: 100

endpoints:
  - name: openai-gpt4
    provider: openai
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    weight: 1
    timeout: 60
    max_retries: 3
    enabled: true

  - name: anthropic-claude
    provider: anthropic
    base_url: https://api.anthropic.com/v1
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-opus-20240229
    weight: 1
    timeout: 60
    max_retries: 3
    enabled: true
```

## API Usage

### Chat Completions

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
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

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');
ws.send(JSON.stringify({messages: [{role: 'user', content: 'Hello'}]}));
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Root info |
| `GET /health` | Health check |
| `GET /stats` | Statistics |
| `GET /logs` | Request logs |
| `POST /keys` | Create API key |
| `POST /chat/completions` | Chat API |
| `POST /v1/chat/completions` | OpenAI-compatible |
| `WS /ws/chat` | WebSocket chat |

## Docker

```bash
docker build -t llm-router .
docker run -p 8000:8000 -v config.yaml:/app/config.yaml llm-router
```

Or use docker-compose:

```bash
docker-compose up -d
```

## Documentation

- [API Docs](http://localhost:8000/docs) - Swagger UI
- [Deployment Guide](./DEPLOYMENT.md)
- [FAQ](./FAQ.md)
- [Benchmark](./BENCHMARK.md)

## License

MIT
