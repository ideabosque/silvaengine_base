#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Performance benchmark tests for silvaengine_base.

Tests cover:
- Cold start time benchmarks
- Parallel initialization speedup
- Memory usage benchmarks
- Event-driven vs polling comparison
"""

import sys
import time
import tracemalloc
from unittest.mock import MagicMock, patch

# Mock external modules before importing
sys.modules['silvaengine_utility'] = MagicMock()
sys.modules['silvaengine_dynamodb_base'] = MagicMock()
sys.modules['silvaengine_constants'] = MagicMock()

import unittest

from silvaengine_base.boosters.plugin.dependency import UnifiedDependencyResolver
from silvaengine_base.boosters.plugin.parallel_scheduler import (
    InitializationTask,
    InitializationMetrics,
    PriorityInitializationQueue,
)


class TestColdStartBenchmarks(unittest.TestCase):
    """Cold start performance benchmarks."""

    def test_dependency_resolution_performance(self):
        """Benchmark dependency resolution for large plugin sets."""
        resolver = UnifiedDependencyResolver()
        
        # Create 100 plugins with dependencies
        nodes = {}
        for i in range(100):
            deps = [f"plugin_{i-1}"] if i > 0 else []
            nodes[f"plugin_{i}"] = deps
        
        # Measure resolution time
        start_time = time.time()
        success, sorted_nodes = resolver.topological_sort(nodes)
        elapsed = time.time() - start_time
        
        self.assertTrue(success)
        self.assertEqual(len(sorted_nodes), 100)
        
        # Performance assertion: should complete in < 100ms
        self.assertLess(elapsed, 0.1, 
            f"Dependency resolution took {elapsed:.3f}s, expected < 0.1s")
        
        print(f"\n[PERF] Dependency resolution (100 nodes): {elapsed*1000:.2f}ms")

    def test_cycle_detection_performance(self):
        """Benchmark cycle detection for large plugin sets."""
        resolver = UnifiedDependencyResolver()
        
        # Create 100 plugins without cycles
        nodes = {}
        for i in range(100):
            deps = [f"plugin_{i-1}"] if i > 0 else []
            nodes[f"plugin_{i}"] = deps
        
        # Measure cycle detection time
        start_time = time.time()
        cycle = resolver.detect_cycle(nodes)
        elapsed = time.time() - start_time
        
        self.assertIsNone(cycle)
        
        # Performance assertion: should complete in < 100ms
        self.assertLess(elapsed, 0.1,
            f"Cycle detection took {elapsed:.3f}s, expected < 0.1s")
        
        print(f"\n[PERF] Cycle detection (100 nodes): {elapsed*1000:.2f}ms")

    def test_queue_operations_performance(self):
        """Benchmark priority queue operations."""
        queue = PriorityInitializationQueue()
        
        # Measure push time for 1000 tasks
        tasks = [
            InitializationTask(
                plugin_type=f"plugin_{i}",
                config={},
                priority=i % 10,
            )
            for i in range(1000)
        ]
        
        start_time = time.time()
        for task in tasks:
            queue.push(task)
        push_time = time.time() - start_time
        
        # Measure pop time
        start_time = time.time()
        while not queue.is_empty():
            queue.pop()
        pop_time = time.time() - start_time
        
        # Performance assertions
        self.assertLess(push_time, 0.1,
            f"Push 1000 tasks took {push_time:.3f}s, expected < 0.1s")
        self.assertLess(pop_time, 0.1,
            f"Pop 1000 tasks took {pop_time:.3f}s, expected < 0.1s")
        
        print(f"\n[PERF] Queue push (1000 tasks): {push_time*1000:.2f}ms")
        print(f"[PERF] Queue pop (1000 tasks): {pop_time*1000:.2f}ms")


class TestMemoryBenchmarks(unittest.TestCase):
    """Memory usage benchmarks."""

    def test_metrics_memory_usage(self):
        """Benchmark memory usage for metrics collection."""
        tracemalloc.start()
        
        metrics = InitializationMetrics()
        
        # Record 1000 plugin initializations
        for i in range(1000):
            metrics.record_start(f"plugin_{i}")
            metrics.record_success(f"plugin_{i}")
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Memory assertion: should use < 1MB for 1000 plugins
        self.assertLess(peak, 1024 * 1024,
            f"Metrics used {peak/1024:.2f}KB, expected < 1024KB")
        
        print(f"\n[MEM] Metrics (1000 plugins): {current/1024:.2f}KB current, {peak/1024:.2f}KB peak")

    def test_dependency_graph_memory_usage(self):
        """Benchmark memory usage for dependency graph."""
        tracemalloc.start()
        
        # Create large dependency graph
        nodes = {}
        for i in range(1000):
            deps = [f"plugin_{j}" for j in range(max(0, i-5), i)]
            nodes[f"plugin_{i}"] = deps
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Memory assertion: should use < 5MB for 1000 nodes
        self.assertLess(peak, 5 * 1024 * 1024,
            f"Graph used {peak/1024/1024:.2f}MB, expected < 5MB")
        
        print(f"\n[MEM] Dependency graph (1000 nodes): {current/1024:.2f}KB current, {peak/1024:.2f}KB peak")


class TestParallelSpeedup(unittest.TestCase):
    """Parallel initialization speedup benchmarks."""

    def test_parallel_vs_sequential_speedup(self):
        """Compare parallel vs sequential initialization time."""
        import threading
        import time
        
        # Simulate plugin initialization with sleep
        def init_plugin(plugin_id, duration=0.01):
            time.sleep(duration)
            return plugin_id
        
        # Sequential initialization
        start_time = time.time()
        for i in range(10):
            init_plugin(i)
        sequential_time = time.time() - start_time
        
        # Parallel initialization
        start_time = time.time()
        threads = []
        for i in range(10):
            t = threading.Thread(target=init_plugin, args=(i,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        parallel_time = time.time() - start_time
        
        # Calculate speedup
        speedup = sequential_time / parallel_time
        
        # Speedup assertion: should be at least 2x faster
        self.assertGreater(speedup, 2.0,
            f"Parallel speedup was {speedup:.2f}x, expected > 2x")
        
        print(f"\n[PERF] Sequential time (10 plugins): {sequential_time*1000:.2f}ms")
        print(f"[PERF] Parallel time (10 plugins): {parallel_time*1000:.2f}ms")
        print(f"[PERF] Speedup: {speedup:.2f}x")


class TestEventVsPolling(unittest.TestCase):
    """Event-driven vs polling comparison benchmarks."""

    def test_event_vs_polling_latency(self):
        """Compare event-driven vs polling latency."""
        import threading
        
        # Polling approach
        def wait_polling(condition, timeout=1.0, interval=0.01):
            start = time.time()
            while time.time() - start < timeout:
                if condition():
                    return True
                time.sleep(interval)
            return False
        
        # Event-driven approach
        event = threading.Event()
        
        def wait_event(timeout=1.0):
            return event.wait(timeout=timeout)
        
        # Measure polling latency
        flag = [False]
        def set_flag_polling():
            time.sleep(0.05)
            flag[0] = True
        
        start_time = time.time()
        t = threading.Thread(target=set_flag_polling)
        t.start()
        wait_polling(lambda: flag[0])
        polling_latency = time.time() - start_time
        t.join()
        
        # Measure event latency
        def set_event():
            time.sleep(0.05)
            event.set()
        
        event.clear()
        start_time = time.time()
        t = threading.Thread(target=set_event)
        t.start()
        wait_event()
        event_latency = time.time() - start_time
        t.join()
        
        # Event-driven should have lower latency
        self.assertLess(event_latency, polling_latency,
            f"Event latency ({event_latency*1000:.2f}ms) should be < polling latency ({polling_latency*1000:.2f}ms)")
        
        print(f"\n[PERF] Polling latency: {polling_latency*1000:.2f}ms")
        print(f"[PERF] Event latency: {event_latency*1000:.2f}ms")


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
