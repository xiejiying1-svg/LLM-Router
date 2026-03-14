/**
 * LLM Router JavaScript/TypeScript SDK
 * 
 * Installation:
 * npm install llm-router
 * 
 * Usage:
 * import { LLMRouter } from 'llm-router';
 * 
 * const router = new LLMRouter({
 *   baseUrl: 'http://localhost:8000',
 *   apiKey: 'your-api-key'
 * });
 * 
 * const response = await router.chat({
 *   messages: [{ role: 'user', content: 'Hello!' }]
 * });
 */

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  model?: string;
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  tenant_id?: string;
}

export interface ChatResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: ChatMessage;
    finish_reason: string;
  }>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface Stats {
  requests_total: number;
  requests_success: number;
  requests_failed: number;
  requests_cached: number;
  success_rate: number;
  tokens_used: number;
  cost_total: number;
  latency_avg_ms: number;
}

export interface Health {
  status: string;
  endpoints_count: number;
  cache_enabled: boolean;
  smart_routing: boolean;
  multi_tenant: boolean;
}

export interface RouterOptions {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
  headers?: Record<string, string>;
}

export class LLMRouterError extends Error {
  constructor(message: string, public statusCode?: number) {
    super(message);
    this.name = 'LLMRouterError';
  }
}

export class RateLimitError extends LLMRouterError {
  constructor(message: string = 'Rate limit exceeded') {
    super(message, 429);
    this.name = 'RateLimitError';
  }
}

export class BadGatewayError extends LLMRouterError {
  constructor(message: string = 'All endpoints failed') {
    super(message, 502);
    this.name = 'BadGatewayError';
  }
}

export class LLMRouter {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;
  private headers: Record<string, string>;

  constructor(options: RouterOptions = {}) {
    this.baseUrl = options.baseUrl || process.env.LLM_ROUTER_URL || 'http://localhost:8000';
    this.apiKey = options.apiKey || process.env.LLM_ROUTER_KEY;
    this.timeout = options.timeout || 60000;
    this.headers = options.headers || {};

    if (this.apiKey) {
      this.headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    this.headers['Content-Type'] = 'application/json';
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = { ...this.headers, ...options.headers };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: AbortSignal.timeout(this.timeout)
      });

      if (!response.ok) {
        if (response.status === 429) {
          throw new RateLimitError();
        } else if (response.status === 502) {
          throw new BadGatewayError();
        }
        const error = await response.text();
        throw new LLMRouterError(error, response.status);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof LLMRouterError) {
        throw error;
      }
      throw new LLMRouterError(error instanceof Error ? error.message : 'Request failed');
    }
  }

  /**
   * Send a chat completion request
   */
  async chat(request: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/v1/chat/completions', {
      method: 'POST',
      body: JSON.stringify(request)
    });
  }

  /**
   * Send a streaming chat completion request
   */
  async *chatStream(request: ChatRequest): AsyncGenerator<string> {
    const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ ...request, stream: true }),
      signal: AbortSignal.timeout(this.timeout)
    });

    if (!response.ok) {
      if (response.status === 429) {
        throw new RateLimitError();
      } else if (response.status === 502) {
        throw new BadGatewayError();
      }
      throw new LLMRouterError('Request failed', response.status);
    }

    if (!response.body) {
      throw new LLMRouterError('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            yield line + '\n';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /**
   * Send batch requests
   */
  async batch(requests: ChatRequest[]): Promise<{ results: any[] }> {
    return this.request<{ results: any[] }>('/v1/batch', {
      method: 'POST',
      body: JSON.stringify({ requests })
    });
  }

  /**
   * Get router statistics
   */
  async getStats(): Promise<Stats> {
    return this.request<Stats>('/stats');
  }

  /**
   * Check router health
   */
  async getHealth(): Promise<Health> {
    return this.request<Health>('/health');
  }

  /**
   * Clear request cache
   */
  async clearCache(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/cache/clear', {
      method: 'POST'
    });
  }

  /**
   * Hot reload configuration
   */
  async reloadConfig(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/config/reload', {
      method: 'POST'
    });
  }

  /**
   * Get Prometheus metrics
   */
  async getMetrics(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/metrics`, {
      headers: this.headers
    });
    return response.text();
  }
}

export default LLMRouter;
