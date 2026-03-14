#!/usr/bin/env python3
"""
LLM Router - 智能大模型路由网关
核心路由逻辑
"""

import os
import yaml
import logging
import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    QUALITY = "quality"
    BALANCED = "balanced"


@dataclass
class Provider:
    """提供商"""
    name: str
    enabled: bool = False
    api_key: str = ""
    base_url: str = ""
    models: List[str] = field(default_factory=list)
    priority: int = 100
    latency: float = 0.0
    success_rate: float = 1.0
    request_count: int = 0
    error_count: int = 0


@dataclass
class RequestStats:
    """请求统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_latency: float = 0.0
    provider_stats: Dict[str, Dict] = field(default_factory=dict)


class LLMRouter:
    """LLM路由器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.providers: Dict[str, Provider] = {}
        self.stats = RequestStats()
        self._init_providers()
        
    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = self.config_path
        if not os.path.exists(config_file):
            logger.warning(f"配置文件 {config_file} 不存在，使用默认配置")
            return self._default_config()
            
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            'providers': {},
            'routing': {
                'default_model': 'gpt-4o-mini',
                'fallback_models': ['gpt-4o-mini'],
                'strategy': 'balanced',
                'timeout': 60,
                'max_retries': 3
            },
            'monitoring': {
                'enabled': True,
                'log_file': 'router.log'
            }
        }
    
    def _init_providers(self):
        """初始化提供商"""
        providers_config = self.config.get('providers', {})
        
        for name, config in providers_config.items():
            if config.get('enabled', False):
                provider = Provider(
                    name=name,
                    enabled=True,
                    api_key=config.get('api_key', ''),
                    base_url=config.get('base_url', ''),
                    models=config.get('models', []),
                    priority=config.get('priority', 100)
                )
                self.providers[name] = provider
                logger.info(f"已加载提供商: {name}")
    
    def get_available_providers(self) -> List[Provider]:
        """获取可用的提供商列表"""
        return [p for p in self.providers.values() if p.enabled]
    
    def select_provider(self, model: str = None, strategy: str = None) -> Optional[Provider]:
        """
        选择最佳提供商
        """
        available = self.get_available_providers()
        if not available:
            logger.error("没有可用的提供商")
            return None
        
        # 如果没指定模型，使用默认模型
        if not model:
            model = self.config.get('routing', {}).get('default_model', 'gpt-4o-mini')
        
        # 如果没指定策略，使用配置中的策略
        if not strategy:
            strategy = self.config.get('routing', {}).get('strategy', 'balanced')
        
        # 根据策略选择
        if strategy == RoutingStrategy.CHEAPEST.value:
            return self._select_cheapest(available, model)
        elif strategy == RoutingStrategy.FASTEST.value:
            return self._select_fastest(available, model)
        elif strategy == RoutingStrategy.QUALITY.value:
            return self._select_quality(available, model)
        else:  # balanced
            return self._select_balanced(available, model)
    
    def _select_cheapest(self, providers: List[Provider], model: str) -> Provider:
        """选择最便宜的"""
        costs = self.config.get('costs', {})
        # 简化：返回第一个可用的，实际应该比较成本
        return providers[0]
    
    def _select_fastest(self, providers: List[Provider], model: str) -> Provider:
        """选择最快的"""
        # 按延迟排序
        sorted_providers = sorted(providers, key=lambda p: p.latency)
        return sorted_providers[0] if sorted_providers else providers[0]
    
    def _select_quality(self, providers: List[Provider], model: str) -> Provider:
        """选择质量最高的"""
        # 按成功率排序
        sorted_providers = sorted(providers, key=lambda p: p.success_rate, reverse=True)
        return sorted_providers[0] if sorted_providers else providers[0]
    
    def _select_balanced(self, providers: List[Provider], model: str) -> Provider:
        """综合选择"""
        # 综合考虑延迟、成功率和优先级
        for p in providers:
            if p.success_rate > 0.9 and p.latency < 10:
                return p
        return providers[0]
    
    def route_request(self, messages: List[Dict], model: str = None, **kwargs) -> Dict:
        """
        路由请求
        """
        routing_config = self.config.get('routing', {})
        max_retries = routing_config.get('max_retries', 3)
        fallback_models = routing_config.get('fallback_models', [])
        
        # 尝试主要模型
        errors = []
        for attempt in range(max_retries):
            provider = self.select_provider(model)
            if not provider:
                break
            
            try:
                logger.info(f"尝试提供商: {provider.name}")
                result = self._call_provider(provider, messages, model, **kwargs)
                
                # 更新统计
                self._update_stats(provider, True)
                return result
                
            except Exception as e:
                logger.warning(f"提供商 {provider.name} 调用失败: {e}")
                errors.append(f"{provider.name}: {str(e)}")
                self._update_stats(provider, False)
                
                # 标记provider失败
                provider.error_count += 1
                provider.success_rate = 1 - (provider.error_count / max(provider.request_count, 1))
        
        # 尝试备用模型
        for fallback_model in fallback_models:
            if fallback_model == model:
                continue
            try:
                logger.info(f"尝试备用模型: {fallback_model}")
                result = self.route_request(messages, fallback_model, **kwargs)
                return result
            except Exception as e:
                logger.warning(f"备用模型 {fallback_model} 失败: {e}")
                continue
        
        return {
            "error": "All providers failed",
            "details": errors
        }
    
    def _call_provider(self, provider: Provider, messages: List[Dict], model: str, **kwargs) -> Dict:
        """
        调用提供商API
        这里应该实现实际的API调用
        """
        # 记录请求
        provider.request_count += 1
        start_time = time.time()
        
        # TODO: 实现实际的API调用
        # 这里返回模拟响应
        response = {
            "id": f"chatcmpl-{os.urandom(8).hex()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "provider": provider.name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a placeholder response. Implement actual API calls in provider modules."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        # 更新延迟
        provider.latency = time.time() - start_time
        
        return response
    
    def _update_stats(self, provider: Provider, success: bool):
        """更新统计信息"""
        self.stats.total_requests += 1
        if success:
            self.stats.successful_requests += 1
        else:
            self.stats.failed_requests += 1
        
        # 更新提供商统计
        if provider.name not in self.stats.provider_stats:
            self.stats.provider_stats[provider.name] = {
                'requests': 0,
                'success': 0,
                'failures': 0,
                'avg_latency': 0
            }
        
        stats = self.stats.provider_stats[provider.name]
        stats['requests'] += 1
        if success:
            stats['success'] += 1
        else:
            stats['failures'] += 1
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        if self.stats.total_requests > 0:
            self.stats.avg_latency = sum(
                p.latency * p.request_count 
                for p in self.providers.values()
            ) / sum(p.request_count for p in self.providers.values())
        
        return {
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "success_rate": self.stats.successful_requests / max(self.stats.total_requests, 1),
            "avg_latency": self.stats.avg_latency,
            "providers": {
                name: {
                    "enabled": p.enabled,
                    "requests": p.request_count,
                    "errors": p.error_count,
                    "success_rate": p.success_rate,
                    "avg_latency": p.latency
                }
                for name, p in self.providers.items()
            }
        }
    
    def health_check(self) -> Dict:
        """健康检查"""
        available = self.get_available_providers()
        return {
            "status": "healthy" if available else "unhealthy",
            "providers_available": len(available),
            "total_providers": len(self.providers),
            "timestamp": datetime.now().isoformat()
        }


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM Router')
    parser.add_argument('--config', '-c', default='config.yaml', help='配置文件路径')
    parser.add_argument('--port', '-p', type=int, default=8000, help='服务端口')
    args = parser.parse_args()
    
    # 初始化路由器
    router = LLMRouter(args.config)
    
    # 打印状态
    print(f"LLM Router 启动完成")
    print(f"可用提供商: {len(router.get_available_providers())}")
    print(f"统计: {router.get_stats()}")


if __name__ == "__main__":
    main()
