# Frequently Asked Questions (FAQ)

## General

### What is LLM Router?
LLM Router is a smart routing layer for Large Language Models that provides:
- Load balancing across multiple LLM providers
- Automatic failover when endpoints fail
- Rate limiting
- API key management
- Request logging and monitoring

### Which providers are supported?
- OpenAI (GPT-4, GPT-3.5 Turbo, etc.)
- Anthropic Claude
- Google Gemini
- Any OpenAI-compatible API

## Configuration

### How do I configure multiple endpoints?
Edit `config.yaml`:

```yaml
endpoints:
  - name: openai-gpt4
    provider: openai
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    enabled: true

  - name: anthropic-claude
    provider: anthropic
    base_url: https://api.anthropic.com/v1
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-opus-20240229
    enabled: true
```

### What load balancing strategies are available?
- **Round Robin**: Cycles through endpoints sequentially
- **Random**: Randomly selects an endpoint
- **Least Connections**: Routes to endpoint with fewest active connections
- **Weighted**: Routes based on weight配置

### How do I set rate limiting?
```yaml
rate_limit: 100  # requests per minute
```

Or per-API key:
```bash
curl -X POST "http://localhost:8000/keys?rate_limit=60"
```

## Usage

### How do I make a chat request?

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7
  }'
```

### How do I enable streaming?
Set `stream: true` in your request:

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

### How do I use WebSocket?
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    messages: [{role: 'user', content: 'Hello!'}]
  }));
};

ws.onmessage = (event) => {
  console.log(event.data);
};
```

## Monitoring

### How do I check endpoint health?
```bash
curl http://localhost:8000/health
```

### How do I view statistics?
```bash
curl http://localhost:8000/stats
```

### How do I view request logs?
```bash
curl "http://localhost:8000/logs?limit=50"
```

## Troubleshooting

### Getting 502 errors
- Check endpoint configuration
- Verify API keys
- Check network connectivity
- Review logs: `curl http://localhost:8000/logs`

### Rate limit errors
- Increase rate limit in config
- Check per-key rate limits
- Monitor usage with `/stats`

### High latency
- Check endpoint timeouts
- Monitor endpoint health
- Add more endpoints for failover

### Authentication errors
- Create API key: `curl -X POST http://localhost:8000/keys`
- Use key in header: `Authorization: Bearer YOUR_KEY`

## Performance

### How many requests can it handle?
Depends on:
- Network latency to LLM providers
- Number of configured endpoints
- Rate limits of upstream providers

### Is it production-ready?
Yes, features include:
- Retry mechanism
- Health checks
- Rate limiting
- Request logging
- Error handling

## Development

### How do I add a new provider?
Extend the `LLMClient` class in `router.py`:

```python
class NewProviderClient(LLMClient):
    async def chat(self, endpoint, messages, temperature, max_tokens, stream):
        # Implement provider-specific logic
        pass
```

### How do I run tests?
```bash
pytest tests/
```

### How do I contribute?
1. Fork the repository
2. Create a feature branch
3. Submit a pull request
