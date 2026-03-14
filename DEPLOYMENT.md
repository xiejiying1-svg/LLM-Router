# LLM Router Deployment Guide

## Table of Contents
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Production Checklist](#production-checklist)
- [Monitoring Setup](#monitoring-setup)
- [Troubleshooting](#troubleshooting)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Edit `config.yaml`:

```yaml
load_balancer: round_robin  # round_robin, random, least_connections, weighted
default_timeout: 60
max_retries: 3
retry_delay: 1.0
rate_limit: 100  # Optional: requests per minute

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

### 3. Run

```bash
# Set environment variables
export OPENAI_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key

# Start the server
python main.py
```

Server runs at `http://localhost:8000`

## Docker Deployment

### Build and Run

```bash
# Build image
docker build -t llm-router .

# Run container
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -e OPENAI_API_KEY=your_key \
  -e ANTHROPIC_API_KEY=your_key \
  llm-router
```

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f router

# Stop services
docker-compose down
```

## Production Checklist

### Security
- [ ] Use environment variables for API keys
- [ ] Enable rate limiting
- [ ] Implement API key authentication
- [ ] Use HTTPS in production
- [ ] Restrict CORS origins
- [ ] Set up firewall rules

### Reliability
- [ ] Configure health checks
- [ ] Set appropriate timeouts
- [ ] Enable retry mechanism
- [ ] Configure multiple endpoints for failover
- [ ] Set up logging and monitoring

### Performance
- [ ] Use connection pooling
- [ ] Configure appropriate rate limits
- [ ] Monitor endpoint health
- [ ] Use weighted load balancing for different capacity endpoints

## Monitoring Setup

### Prometheus Metrics

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'llm-router'
    static_configs:
      - targets: ['router:8000']
```

### Grafana Dashboard

Import the dashboard from `grafana/dashboards/router.json` for:
- Request rate
- Success/failure rate
- Response time
- Endpoint health

## Troubleshooting

### Common Issues

**1. All endpoints returning 502**
- Check endpoint configuration
- Verify API keys are correct
- Check network connectivity

**2. Rate limiting triggered**
- Increase rate limit in config
- Check for stuck requests

**3. High latency**
- Check endpoint timeout settings
- Monitor endpoint health
- Consider adding more endpoints

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python main.py
```

### Health Check

```bash
curl http://localhost:8000/health
```

### View Stats

```bash
curl http://localhost:8000/stats
```
