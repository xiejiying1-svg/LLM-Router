#!/usr/bin/env python3
"""
LLM Router CLI Tool
"""
import argparse
import json
import os
import sys
import requests
from typing import Optional


class LLMRouterCLI:
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = None):
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("LLM_ROUTER_KEY")
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("headers", self.headers)
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def chat(self, message: str, model: str = None, stream: bool = False, json_output: bool = False):
        """Send chat message"""
        payload = {
            "messages": [{"role": "user", "content": message}],
            "stream": stream
        }
        if model:
            payload["model"] = model

        if stream:
            url = f"{self.base_url}/v1/chat/completions"
            self.headers["Accept"] = "text/event-stream"
            response = requests.post(url, json=payload, headers=self.headers, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        print(line)
            return

        result = self._request("POST", "/v1/chat/completions", json=payload)

        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            content = result["choices"][0]["message"]["content"]
            print(content)

    def stats(self, json_output: bool = False):
        """Get statistics"""
        result = self._request("GET", "/stats")
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"Total Requests: {result['requests_total']}")
            print(f"Success: {result['requests_success']}")
            print(f"Failed: {result['requests_failed']}")
            print(f"Cached: {result['requests_cached']}")
            print(f"Success Rate: {result['success_rate']:.2%}")
            print(f"Tokens Used: {result['tokens_used']}")
            print(f"Total Cost: ${result['cost_total']:.4f}")
            print(f"Avg Latency: {result['latency_avg_ms']:.2f}ms")

    def health(self, json_output: bool = False):
        """Check health"""
        result = self._request("GET", "/health")
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"Status: {result['status']}")
            print(f"Endpoints: {result['endpoints_count']}")
            print(f"Cache: {'Enabled' if result['cache_enabled'] else 'Disabled'}")
            print(f"Smart Routing: {'Enabled' if result['smart_routing'] else 'Disabled'}")
            print(f"Multi-Tenant: {'Enabled' if result['multi_tenant'] else 'Disabled'}")

    def metrics(self):
        """Get Prometheus metrics"""
        result = self._request("GET", "/metrics")
        print(result)

    def cache_clear(self):
        """Clear cache"""
        result = self._request("POST", "/cache/clear")
        print(result["status"])

    def config_reload(self):
        """Reload configuration"""
        result = self._request("POST", "/config/reload")
        print(result["status"])

    def batch(self, messages: list[str], json_output: bool = False):
        """Send batch requests"""
        requests_data = [
            {"messages": [{"role": "user", "content": msg}]}
            for msg in messages
        ]
        result = self._request("POST", "/v1/batch", json={"requests": requests_data})

        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for i, r in enumerate(result["results"]):
                print(f"\n--- Request {i+1} ---")
                if r["success"]:
                    print(r["data"]["choices"][0]["message"]["content"])
                else:
                    print(f"Error: {r['error']}")


def main():
    parser = argparse.ArgumentParser(description="LLM Router CLI")
    parser.add_argument("--url", default=os.environ.get("LLM_ROUTER_URL", "http://localhost:8000"), help="Router URL")
    parser.add_argument("--key", default=os.environ.get("LLM_ROUTER_KEY"), help="API Key")
    parser.add_argument("--json", action="store_true", help="JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # chat
    chat_parser = subparsers.add_parser("chat", help="Send chat message")
    chat_parser.add_argument("message", help="Message to send")
    chat_parser.add_argument("--model", help="Model to use")
    chat_parser.add_argument("--stream", action="store_true", help="Stream response")

    # stats
    subparsers.add_parser("stats", help="Get statistics")

    # health
    subparsers.add_parser("health", help="Check health")

    # metrics
    subparsers.add_parser("metrics", help="Get Prometheus metrics")

    # cache-clear
    subparsers.add_parser("cache-clear", help="Clear cache")

    # config-reload
    subparsers.add_parser("config-reload", help="Reload configuration")

    # batch
    batch_parser = subparsers.add_parser("batch", help="Send batch requests")
    batch_parser.add_argument("messages", nargs="+", help="Messages to send")

    args = parser.parse_args()

    cli = LLMRouterCLI(base_url=args.url, api_key=args.key)

    try:
        if args.command == "chat":
            cli.chat(args.message, args.model, args.stream, args.json)
        elif args.command == "stats":
            cli.stats(args.json)
        elif args.command == "health":
            cli.health(args.json)
        elif args.command == "metrics":
            cli.metrics()
        elif args.command == "cache-clear":
            cli.cache_clear()
        elif args.command == "config-reload":
            cli.config_reload()
        elif args.command == "batch":
            cli.batch(args.messages, args.json)
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
