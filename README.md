# LLM Router - 智能大模型路由网关

English | [中文](./README_CN.md)

A powerful LLM gateway that aggregates multiple LLM providers with intelligent routing, automatic failover, monitoring and alerting.

## Features

- 🔄 **Intelligent Routing** - Automatically selects the best provider based on response time, price, and quality
- 🛡️ **Automatic Failover** - Automatically switches to backup provider when one fails
- 📊 **Real-time Monitoring** - Track API usage, costs, latency and success rates
- 🔔 **Smart Alerting** - Notify when issues occur or quotas are low
- 💰 **Cost Optimization** - Route requests to the most cost-effective provider
- 🌐 **Unified API** - Single endpoint for multiple LLM providers

## Supported Providers

| Provider | Status |
|----------|--------|
| OpenAI | ✅ |
| Anthropic (Claude) | ✅ |
| Google (Gemini) | ✅ |
| DeepSeek | ✅ |
| Moonshot (Kimi) | ✅ |
| Zhipu (GLM) | ✅ |
| SiliconFlow | ✅ |
| OpenRouter | ✅ |

## Quick Start

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/LLM-Router.git
cd LLM-Router
pip install -r requirements.txt
```

### Configuration

Copy `config.example.yaml` to `config.yaml` and add your API keys:

```yaml
providers:
  openai:
    api_key: your-openai-key
    base_url: https://api.openai.com/v1
    
  anthropic:
    api_key: your-anthropic-key
    
  deepseek:
    api_key: your-deepseek-key

routing:
  default_model: gpt-4o-mini
  fallback_models:
    - gpt-4o-mini
    - claude-3-haiku
    - deepseek-chat

monitoring:
  enabled: true
  log_file: router.log
```

### Run

```bash
python main.py
```

### Use via API

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completion |
| `/v1/models` | GET | List available models |
| `/health` | GET | Health check |
| `/stats` | GET | Usage statistics |

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
┌──────▼──────┐
│  Router     │  ← Intelligent routing logic
└──────┬──────┘
       │
┌──────▼──────┐
│  Providers  │  ← OpenAI, Claude, Gemini...
└─────────────┘
       │
┌──────▼──────┐
│  Monitor    │  ← Logging & alerting
└─────────────┘
```

## Use Cases

- **Cost Optimization** - Route to cheaper providers during high traffic
- **Reliability** - Automatic failover ensures 99.9% uptime
- **Development** - Easy switching between providers during development
- **Research** - Compare responses across different models

## License

MIT License

---

Made with ❤️ for the AI Community
