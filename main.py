#!/usr/bin/env python3
"""
LLM Router - FastAPI 服务入口
"""

import os
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import uvicorn

from router import LLMRouter

# 加载配置
def load_config():
    config_path = os.environ.get('CONFIG_PATH', 'config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

app = FastAPI(
    title="LLM Router",
    description="智能大模型路由网关 - Intelligent LLM Gateway",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化路由器
config = load_config()
router = LLMRouter()


# ============ 数据模型 ============

class Message(BaseModel):
    role: str = Field(..., description="角色: system, user, assistant")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-4o-mini", description="模型名称")
    messages: List[Message] = Field(..., description="消息列表")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None)
    stream: Optional[bool] = Field(default=False)
    **kwargs: Any


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    provider: str
    choices: List[Dict]
    usage: Dict


# ============ API 端点 ============

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "LLM Router",
        "version": "1.0.0",
        "description": "智能大模型路由网关"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return router.health_check()


@app.get("/v1/models")
async def list_models():
    """列出可用模型"""
    models = []
    for name, provider in router.providers.items():
        if provider.enabled:
            for model in provider.models:
                models.append({
                    "id": model,
                    "object": "model",
                    "owned_by": name,
                    "provider": name
                })
    
    # 添加默认模型
    if not models:
        models = [
            {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai", "provider": "openai"},
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek", "provider": "deepseek"},
            {"id": "glm-4-flash", "object": "model", "owned_by": "zhipu", "provider": "zhipu"},
        ]
    
    return {
        "object": "list",
        "data": models
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    聊天补全接口
    """
    try:
        # 转换消息格式
        messages = [msg.dict() for msg in request.messages]
        
        # 调用路由器
        result = router.route_request(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            **request.kwargs
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """获取使用统计"""
    return router.get_stats()


# ============ 主程序 ============

def main():
    """启动服务"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM Router API Server')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8000, help='监听端口')
    parser.add_argument('--config', default='config.yaml', help='配置文件')
    args = parser.parse_args()
    
    # 设置配置路径
    os.environ['CONFIG_PATH'] = args.config
    
    print(f"🚀 LLM Router 启动中...")
    print(f"📡 服务地址: http://{args.host}:{args.port}")
    print(f"📖 API 文档: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
