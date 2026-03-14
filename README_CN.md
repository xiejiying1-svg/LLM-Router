# LLM Router - 智能大模型路由网关

[English](./README.md) | 中文

一个强大的LLM网关，聚合多个大模型提供商，提供智能路由、自动容错、监控和告警功能。

## ✨ 特性

- 🔄 **智能路由** - 根据响应时间、价格和质量自动选择最佳提供商
- 🛡️ **自动容错** - 主提供商失败时自动切换到备用提供商
- 📊 **实时监控** - 跟踪API使用情况、成本、延迟和成功率
- 🔔 **智能告警** - 问题发生时或配额过低时通知
- 💰 **成本优化** - 将请求路由到最具成本效益的提供商
- 🌐 **统一API** - 单个端点对接多个大模型提供商

## 🏢 支持的提供商

| 提供商 | 状态 |
|--------|------|
| OpenAI | ✅ |
| Anthropic (Claude) | ✅ |
| Google (Gemini) | ✅ |
| DeepSeek | ✅ |
| Moonshot (Kimi) | ✅ |
| 智谱 (GLM) | ✅ |
| SiliconFlow | ✅ |
| OpenRouter | ✅ |

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/YOUR_USERNAME/LLM-Router.git
cd LLM-Router
pip install -r requirements.txt
```

### 配置

复制 `config.example.yaml` 为 `config.yaml` 并填入你的API密钥：

```yaml
providers:
  openai:
    enabled: true
    api_key: your-openai-key
    
  deepseek:
    enabled: true
    api_key: your-deepseek-key
    
  zhipu:
    enabled: true
    api_key: your-zhipu-key

routing:
  default_model: gpt-4o-mini
  strategy: balanced
```

### 运行

```bash
# 启动API服务
python main.py --port 8000

# 或使用路由器
python router.py
```

### 使用API

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "你好!"}]
  }'
```

## 📡 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全 |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |
| `/stats` | GET | 使用统计 |

## 🏗️ 架构

```
┌─────────────┐
│   客户端    │
└──────┬──────┘
       │
┌──────▼──────┐
│  路由器     │  ← 智能路由逻辑
└──────┬──────┘
       │
┌──────▼──────┐
│  提供商     │  ← OpenAI, Claude, Gemini...
└─────────────┘
       │
┌──────▼──────┐
│  监控       │  ← 日志和告警
└─────────────┘
```

## 💡 使用场景

- **成本优化** - 高峰期路由到更便宜的提供商
- **高可靠性** - 自动容错确保99.9%正常运行时间
- **开发测试** - 轻松在不同提供商之间切换
- **研究对比** - 对比不同模型的回复效果

## 📝 配置说明

### 路由策略

- `fastest` - 选择响应最快的提供商
- `cheapest` - 选择成本最低的提供商
- `quality` - 选择质量最高的提供商
- `balanced` - 综合考虑选择（推荐）

### 提供商配置

每个提供商可以配置：
- `enabled` - 是否启用
- `api_key` - API密钥
- `base_url` - API地址
- `models` - 支持的模型列表
- `priority` - 优先级（数字越小越高）

## 🛠️ 扩展开发

项目采用模块化设计，可以轻松添加新的提供商：

```python
# 在 router.py 中添加新的提供商类
class NewProvider(Provider):
    def __init__(self, config):
        super().__init__("new_provider", config)
    
    def call(self, messages, model, **kwargs):
        # 实现API调用
        pass
```

## 📄 许可证

MIT License

---

❤️ 为AI社区而生
