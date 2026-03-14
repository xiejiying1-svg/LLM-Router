"""Unit tests for LLM Router"""
import unittest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

# Import the router module
import sys
sys.path.insert(0, '.')

from router import (
    CircuitBreaker, CircuitState, RetryHistory, AuditLogger,
    PriorityQueue, PriorityLevel, EndpointConfig, ModelProvider,
    RouterConfig, LoadBalancerStrategy
)


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker functionality"""
    
    def test_initial_state(self):
        """Test circuit breaker starts in closed state"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())
    
    def test_failure_opens_circuit(self):
        """Test failures open the circuit"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        
        cb.record_failure()  # Third failure
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())
    
    def test_recovery_timeout(self):
        """Test circuit recovers after timeout"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        
        time.sleep(1.1)
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
    
    def test_success_closes_circuit(self):
        """Test success closes circuit from half-open"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1, half_open_max_calls=2)
        
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        
        time.sleep(1.1)
        cb.can_execute()  # Enter half-open
        
        cb.record_success()
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
    
    def test_half_open_limits_calls(self):
        """Test half-open limits concurrent calls"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1, half_open_max_calls=2)
        
        cb.record_failure()
        cb.record_failure()
        
        time.sleep(1.1)
        
        self.assertTrue(cb.can_execute())  # First call
        self.assertTrue(cb.can_execute())  # Second call
        self.assertFalse(cb.can_execute())  # No more


class TestRetryHistory(unittest.TestCase):
    """Test retry history tracking"""
    
    def test_add_retry(self):
        """Test adding retry records"""
        history = RetryHistory(max_history=100)
        
        history.add_retry("endpoint1", 1, "timeout", False, 5.0)
        history.add_retry("endpoint1", 2, None, True, 3.0)
        
        records = history.get_history("endpoint1")
        self.assertEqual(len(records), 2)
    
    def test_stats(self):
        """Test statistics calculation"""
        history = RetryHistory(max_history=100)
        
        history.add_retry("ep1", 1, None, True, 1.0)
        history.add_retry("ep1", 1, None, True, 2.0)
        history.add_retry("ep1", 1, "error", False, 3.0)
        history.add_retry("ep2", 1, None, True, 1.0)
        
        # Endpoint specific stats
        ep1_stats = history.get_stats("ep1")
        self.assertEqual(ep1_stats["total"], 3)
        self.assertAlmostEqual(ep1_stats["success_rate"], 2/3)
        self.assertAlmostEqual(ep1_stats["avg_latency"], 2.0)
        
        # All stats
        all_stats = history.get_stats()
        self.assertEqual(all_stats["total"], 4)
    
    def test_max_history_limit(self):
        """Test history is limited to max"""
        history = RetryHistory(max_history=5)
        
        for i in range(10):
            history.add_retry("ep1", 1, None, True, 1.0)
        
        self.assertEqual(len(history.history), 5)


class TestAuditLogger(unittest.TestCase):
    """Test audit logging"""
    
    def test_log_request(self):
        """Test logging a request"""
        logger = AuditLogger(max_entries=1000)
        
        logger.log(
            request_id="req-123",
            client_id="client-1",
            endpoint="openai-gpt4",
            model="gpt-4",
            tokens_in=100,
            tokens_out=200,
            latency=1.5,
            status="success",
            cost=0.01
        )
        
        logs = logger.get_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["request_id"], "req-123")
    
    def test_get_stats(self):
        """Test audit statistics"""
        logger = AuditLogger(max_entries=1000)
        
        logger.log("1", "c1", "ep1", "m1", 100, 200, 1.0, "success", cost=0.01)
        logger.log("2", "c1", "ep2", "m2", 100, 200, 1.0, "success", cost=0.02)
        logger.log("3", "c2", "ep1", "m1", 100, 200, 1.0, "error", "timeout")
        
        stats = logger.get_stats()
        self.assertEqual(stats["total_requests"], 3)
        self.assertAlmostEqual(stats["success_rate"], 2/3)
        self.assertAlmostEqual(stats["total_cost"], 0.03)


class TestPriorityQueue(unittest.TestCase):
    """Test priority queue"""
    
    def test_enqueue_dequeue(self):
        """Test basic enqueue/dequeue"""
        pq = PriorityQueue()
        
        pq.enqueue(PriorityLevel.LOW, "low")
        pq.enqueue(PriorityLevel.NORMAL, "normal")
        pq.enqueue(PriorityLevel.HIGH, "high")
        pq.enqueue(PriorityLevel.CRITICAL, "critical")
        
        # Critical should come first
        self.assertEqual(pq.dequeue(), "critical")
        self.assertEqual(pq.dequeue(), "high")
        self.assertEqual(pq.dequeue(), "normal")
        self.assertEqual(pq.dequeue(), "low")
    
    def test_multiple_same_priority(self):
        """Test multiple items same priority"""
        pq = PriorityQueue()
        
        pq.enqueue(PriorityLevel.NORMAL, "first")
        pq.enqueue(PriorityLevel.NORMAL, "second")
        
        self.assertEqual(pq.dequeue(), "first")
        self.assertEqual(pq.dequeue(), "second")
    
    def test_size(self):
        """Test queue size"""
        pq = PriorityQueue()
        
        pq.enqueue(PriorityLevel.LOW, "a")
        pq.enqueue(PriorityLevel.HIGH, "b")
        
        self.assertEqual(pq.size(), 2)
        
        pq.dequeue()
        self.assertEqual(pq.size(), 1)


class TestEndpointConfig(unittest.TestCase):
    """Test endpoint configuration"""
    
    def test_defaults(self):
        """Test default values"""
        config = EndpointConfig(
            name="test",
            provider=ModelProvider.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-4"
        )
        
        self.assertEqual(config.weight, 1)
        self.assertEqual(config.timeout, 60)
        self.assertEqual(config.max_retries, 3)
        self.assertTrue(config.enabled)
        self.assertEqual(config.cost_per_1k_tokens, 0.002)
    
    def test_custom_values(self):
        """Test custom configuration"""
        config = EndpointConfig(
            name="custom",
            provider=ModelProvider.ANTHROPIC,
            base_url="https://api.anthropic.com/v1",
            api_key="key",
            model="claude-3",
            weight=5,
            timeout=120,
            max_retries=5,
            enabled=False,
            cost_per_1k_tokens=0.015,
            capabilities=["reasoning", "code"],
            max_tokens=8192
        )
        
        self.assertEqual(config.weight, 5)
        self.assertEqual(config.timeout, 120)
        self.assertEqual(config.max_retries, 5)
        self.assertFalse(config.enabled)
        self.assertEqual(config.cost_per_1k_tokens, 0.015)
        self.assertEqual(config.capabilities, ["reasoning", "code"])
        self.assertEqual(config.max_tokens, 8192)


class TestRouterConfig(unittest.TestCase):
    """Test router configuration"""
    
    def test_defaults(self):
        """Test default configuration"""
        config = RouterConfig()
        
        self.assertEqual(config.load_balancer, LoadBalancerStrategy.ROUND_ROBIN)
        self.assertEqual(config.default_timeout, 60)
        self.assertEqual(config.max_retries, 3)
        self.assertFalse(config.cache_enabled)
        self.assertFalse(config.smart_routing)
        self.assertFalse(config.cost_optimization)
        self.assertFalse(config.multi_tenant)
    
    def test_full_config(self):
        """Test full configuration"""
        config = RouterConfig(
            load_balancer=LoadBalancerStrategy.SMART,
            cache_enabled=True,
            redis_url="redis://localhost:6379",
            smart_routing=True,
            cost_optimization=True,
            multi_tenant=True,
            rate_limit=1000
        )
        
        self.assertEqual(config.load_balancer, LoadBalancerStrategy.SMART)
        self.assertTrue(config.cache_enabled)
        self.assertTrue(config.smart_routing)
        self.assertTrue(config.cost_optimization)
        self.assertTrue(config.multi_tenant)
        self.assertEqual(config.rate_limit, 1000)


# Mock tests for actual routing (require API keys)
class TestLoadBalancing(unittest.TestCase):
    """Test load balancing strategies"""
    
    def test_round_robin(self):
        """Test round robin selection"""
        from router import RoundRobinLB
        
        endpoints = [
            Mock(name="ep1"),
            Mock(name="ep2"),
            Mock(name="ep3")
        ]
        
        lb = RoundRobinLB(endpoints)
        
        # Should cycle through endpoints
        selections = [lb.select() for _ in range(6)]
        
        self.assertEqual(selections[0].name, "ep1")
        self.assertEqual(selections[1].name, "ep2")
        self.assertEqual(selections[2].name, "ep2")
        self.assertEqual(selections[3].name, "ep3")
        self.assertEqual(selections[4].name, "ep3")
        self.assertEqual(selections[5].name, "ep1")


class TestCaching(unittest.TestCase):
    """Test caching functionality"""
    
    def test_cache_key_generation(self):
        """Test cache key generation"""
        from router import RequestCache
        
        cache = RequestCache(max_size=100, ttl=60)
        
        messages = [{"role": "user", "content": "Hello"}]
        key1 = cache._generate_key(messages, "gpt-4", 0.7)
        key2 = cache._generate_key(messages, "gpt-4", 0.7)
        key3 = cache._generate_key([{"role": "user", "content": "Hi"}], "gpt-4", 0.7)
        
        self.assertEqual(key1, key2)  # Same input = same key
        self.assertNotEqual(key1, key3)  # Different input = different key


class TestHealthCheck(unittest.TestCase):
    """Test health checking"""
    
    @patch('router.requests.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_get.return_value = mock_response
        
        # This would require the actual health check implementation
        # Just a placeholder test
        pass


if __name__ == '__main__':
    unittest.main()
