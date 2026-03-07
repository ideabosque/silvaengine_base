#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for CircuitBreaker module.

Tests cover:
- Circuit breaker state transitions
- Failure threshold handling
- Recovery timeout handling
- Half-open state behavior
- CircuitBreakerRegistry functionality
"""

import threading
import time
import unittest
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, "/Users/Garabateador/Workspace/abacusipllc/backend/gpt/silvaengine_base")

from silvaengine_base.boosters.plugin.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker_registry,
)


class TestCircuitBreaker(unittest.TestCase):
    """Test CircuitBreaker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=1.0,
            half_open_max_calls=1,
            name="test_breaker",
        )

    def test_initial_state_is_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        self.assertEqual(self.breaker.get_state(), CircuitState.CLOSED)

    def test_successful_call_remains_closed(self):
        """Test successful calls keep circuit closed."""
        def success_func():
            return "success"
        
        for _ in range(5):
            result = self.breaker.call(success_func)
            self.assertEqual(result, "success")
        
        self.assertEqual(self.breaker.get_state(), CircuitState.CLOSED)

    def test_failure_threshold_opens_circuit(self):
        """Test circuit opens after reaching failure threshold."""
        def failing_func():
            raise ValueError("Test error")
        
        for _ in range(3):
            with self.assertRaises(ValueError):
                self.breaker.call(failing_func)
        
        self.assertEqual(self.breaker.get_state(), CircuitState.OPEN)

    def test_open_circuit_blocks_calls(self):
        """Test OPEN circuit blocks subsequent calls."""
        self.breaker._state = CircuitState.OPEN
        self.breaker._last_failure_time = time.time()
        
        with self.assertRaises(Exception) as context:
            self.breaker.call(lambda: "success")
        
        self.assertIn("Circuit breaker 'test_breaker' is OPEN", str(context.exception))

    def test_recovery_timeout_transitions_to_half_open(self):
        """Test circuit transitions to HALF_OPEN after recovery timeout."""
        self.breaker._state = CircuitState.OPEN
        self.breaker._last_failure_time = time.time() - 2.0  # 2 seconds ago
        
        state = self.breaker.get_state()
        self.assertEqual(state, CircuitState.HALF_OPEN)

    def test_half_open_success_closes_circuit(self):
        """Test successful call in HALF_OPEN closes circuit."""
        self.breaker._state = CircuitState.HALF_OPEN
        self.breaker._half_open_calls = 0
        
        result = self.breaker.call(lambda: "success")
        
        self.assertEqual(result, "success")
        self.assertEqual(self.breaker.get_state(), CircuitState.CLOSED)

    def test_half_open_failure_reopens_circuit(self):
        """Test failed call in HALF_OPEN reopens circuit."""
        self.breaker._state = CircuitState.HALF_OPEN
        self.breaker._half_open_calls = 0
        
        with self.assertRaises(ValueError):
            self.breaker.call(lambda: (_ for _ in ()).throw(ValueError("Test error")))
        
        self.assertEqual(self.breaker.get_state(), CircuitState.OPEN)

    def test_half_open_max_calls_limit(self):
        """Test HALF_OPEN state limits concurrent calls."""
        self.breaker._state = CircuitState.HALF_OPEN
        self.breaker._half_open_calls = self.breaker._half_open_max_calls
        
        with self.assertRaises(Exception) as context:
            self.breaker.call(lambda: "success")
        
        self.assertIn("max calls reached", str(context.exception))

    def test_get_stats(self):
        """Test get_stats returns correct statistics."""
        stats = self.breaker.get_stats()
        
        self.assertEqual(stats["name"], "test_breaker")
        self.assertEqual(stats["state"], "closed")
        self.assertEqual(stats["failure_count"], 0)
        self.assertEqual(stats["success_count"], 0)
        self.assertEqual(stats["failure_threshold"], 3)
        self.assertEqual(stats["recovery_timeout"], 1.0)

    def test_reset(self):
        """Test reset returns to initial state."""
        self.breaker._state = CircuitState.OPEN
        self.breaker._failure_count = 5
        self.breaker._success_count = 3
        self.breaker._last_failure_time = time.time()
        
        self.breaker.reset()
        
        self.assertEqual(self.breaker.get_state(), CircuitState.CLOSED)
        self.assertEqual(self.breaker._failure_count, 0)
        self.assertEqual(self.breaker._success_count, 0)
        self.assertIsNone(self.breaker._last_failure_time)


class TestCircuitBreakerRegistry(unittest.TestCase):
    """Test CircuitBreakerRegistry class."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = CircuitBreakerRegistry()

    def test_get_or_create_creates_new_breaker(self):
        """Test get_or_create creates new circuit breaker."""
        breaker = self.registry.get_or_create("test_plugin")
        
        self.assertIsNotNone(breaker)
        self.assertEqual(breaker._name, "test_plugin")

    def test_get_or_create_returns_existing_breaker(self):
        """Test get_or_create returns existing circuit breaker."""
        breaker1 = self.registry.get_or_create("test_plugin")
        breaker2 = self.registry.get_or_create("test_plugin")
        
        self.assertIs(breaker1, breaker2)

    def test_get_returns_none_for_nonexistent(self):
        """Test get returns None for nonexistent breaker."""
        result = self.registry.get("nonexistent")
        self.assertIsNone(result)

    def test_get_returns_existing_breaker(self):
        """Test get returns existing circuit breaker."""
        created = self.registry.get_or_create("test_plugin")
        retrieved = self.registry.get("test_plugin")
        
        self.assertIs(created, retrieved)

    def test_remove_existing_breaker(self):
        """Test remove deletes existing breaker."""
        self.registry.get_or_create("test_plugin")
        
        result = self.registry.remove("test_plugin")
        
        self.assertTrue(result)
        self.assertIsNone(self.registry.get("test_plugin"))

    def test_remove_nonexistent_breaker(self):
        """Test remove returns False for nonexistent breaker."""
        result = self.registry.remove("nonexistent")
        self.assertFalse(result)

    def test_get_all_stats(self):
        """Test get_all_stats returns all breaker stats."""
        self.registry.get_or_create("plugin_a", failure_threshold=2)
        self.registry.get_or_create("plugin_b", failure_threshold=5)
        
        stats = self.registry.get_all_stats()
        
        self.assertIn("plugin_a", stats)
        self.assertIn("plugin_b", stats)
        self.assertEqual(stats["plugin_a"]["failure_threshold"], 2)
        self.assertEqual(stats["plugin_b"]["failure_threshold"], 5)

    def test_reset_all(self):
        """Test reset_all resets all breakers."""
        breaker_a = self.registry.get_or_create("plugin_a")
        breaker_b = self.registry.get_or_create("plugin_b")
        
        breaker_a._state = CircuitState.OPEN
        breaker_b._state = CircuitState.OPEN
        
        self.registry.reset_all()
        
        self.assertEqual(breaker_a.get_state(), CircuitState.CLOSED)
        self.assertEqual(breaker_b.get_state(), CircuitState.CLOSED)


class TestCircuitBreakerThreadSafety(unittest.TestCase):
    """Test circuit breaker thread safety."""

    def test_concurrent_calls(self):
        """Test circuit breaker handles concurrent calls safely."""
        breaker = CircuitBreaker(failure_threshold=10, name="concurrent_test")
        success_count = [0]
        failure_count = [0]
        lock = threading.Lock()
        
        def worker():
            try:
                breaker.call(lambda: None)
                with lock:
                    success_count[0] += 1
            except Exception:
                with lock:
                    failure_count[0] += 1
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(success_count[0], 10)
        self.assertEqual(failure_count[0], 0)

    def test_concurrent_failure_threshold(self):
        """Test circuit breaker handles concurrent failures safely."""
        breaker = CircuitBreaker(failure_threshold=5, name="concurrent_failure_test")
        
        def failing_worker():
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("Test")))
            except ValueError:
                pass
        
        threads = [threading.Thread(target=failing_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(breaker.get_state(), CircuitState.OPEN)


class TestGetCircuitBreakerRegistry(unittest.TestCase):
    """Test get_circuit_breaker_registry function."""

    def test_returns_singleton(self):
        """Test get_circuit_breaker_registry returns singleton."""
        registry1 = get_circuit_breaker_registry()
        registry2 = get_circuit_breaker_registry()
        
        self.assertIs(registry1, registry2)


if __name__ == "__main__":
    unittest.main()
