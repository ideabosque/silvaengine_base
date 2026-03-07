#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for ParallelInitializationScheduler module.

Tests cover:
- InitializationTask dataclass
- InitializationMetrics collection
- PriorityInitializationQueue operations
- ParallelInitializationScheduler scheduling
- Dependency resolution
- Cycle detection
- Topological sorting
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock

# Mock silvaengine_utility before importing any silvaengine modules
mock_invoker_module = MagicMock()
mock_invoker_module.Invoker = MagicMock()
sys.modules['silvaengine_utility'] = mock_invoker_module
sys.modules['silvaengine_dynamodb_base'] = MagicMock()
sys.modules['silvaengine_dynamodb_base.models'] = MagicMock()
sys.modules['silvaengine_constants'] = MagicMock()

import threading
import time
import unittest
from unittest.mock import Mock, patch

from silvaengine_base.boosters.plugin.parallel_scheduler import (
    InitializationTask,
    InitializationMetrics,
    PriorityInitializationQueue,
    ParallelInitializationScheduler,
)


class TestInitializationTask(unittest.TestCase):
    """Test InitializationTask dataclass."""

    def test_create_task_with_defaults(self):
        """Test creating task with default values."""
        task = InitializationTask(
            plugin_type="test_plugin",
            config={"key": "value"},
        )
        
        self.assertEqual(task.plugin_type, "test_plugin")
        self.assertEqual(task.config, {"key": "value"})
        self.assertEqual(task.dependencies, [])
        self.assertEqual(task.priority, 0)
        self.assertEqual(task.timeout, 30.0)

    def test_create_task_with_all_fields(self):
        """Test creating task with all fields."""
        task = InitializationTask(
            plugin_type="test_plugin",
            config={"key": "value"},
            dependencies=["dep1", "dep2"],
            priority=10,
            timeout=60.0,
        )
        
        self.assertEqual(task.plugin_type, "test_plugin")
        self.assertEqual(task.config, {"key": "value"})
        self.assertEqual(task.dependencies, ["dep1", "dep2"])
        self.assertEqual(task.priority, 10)
        self.assertEqual(task.timeout, 60.0)


class TestInitializationMetrics(unittest.TestCase):
    """Test InitializationMetrics class."""

    def setUp(self):
        """Set up test fixtures."""
        self.metrics = InitializationMetrics()

    def test_record_start(self):
        """Test recording start time."""
        self.metrics.record_start("plugin_a")
        
        self.assertIn("plugin_a", self.metrics._start_times)
        self.assertIsNotNone(self.metrics._global_start_time)

    def test_record_success(self):
        """Test recording successful initialization."""
        self.metrics.record_start("plugin_a")
        self.metrics.record_success("plugin_a")
        
        self.assertIn("plugin_a", self.metrics._successes)
        self.assertIn("plugin_a", self.metrics._end_times)

    def test_record_failure(self):
        """Test recording failed initialization."""
        self.metrics.record_start("plugin_a")
        self.metrics.record_failure("plugin_a", "Test error")
        
        self.assertIn("plugin_a", self.metrics._failures)
        self.assertEqual(self.metrics._failures["plugin_a"], "Test error")

    def test_get_plugin_duration(self):
        """Test getting plugin duration."""
        self.metrics.record_start("plugin_a")
        time.sleep(0.01)  # Small delay
        self.metrics.record_success("plugin_a")
        
        duration = self.metrics.get_plugin_duration("plugin_a")
        
        self.assertIsNotNone(duration)
        self.assertGreater(duration, 0)

    def test_get_plugin_duration_not_found(self):
        """Test getting duration for nonexistent plugin."""
        duration = self.metrics.get_plugin_duration("nonexistent")
        self.assertIsNone(duration)

    def test_get_summary(self):
        """Test getting metrics summary."""
        self.metrics.record_start("plugin_a")
        self.metrics.record_success("plugin_a")
        
        self.metrics.record_start("plugin_b")
        self.metrics.record_failure("plugin_b", "Test error")
        
        summary = self.metrics.get_summary()
        
        self.assertEqual(summary["total_plugins"], 2)
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertIn("plugin_a", summary["plugin_details"])
        self.assertIn("plugin_b", summary["plugin_details"])

    def test_reset(self):
        """Test resetting metrics."""
        self.metrics.record_start("plugin_a")
        self.metrics.record_success("plugin_a")
        
        self.metrics.reset()
        
        self.assertEqual(len(self.metrics._start_times), 0)
        self.assertEqual(len(self.metrics._successes), 0)


class TestPriorityInitializationQueue(unittest.TestCase):
    """Test PriorityInitializationQueue class."""

    def setUp(self):
        """Set up test fixtures."""
        self.queue = PriorityInitializationQueue()

    def test_push_and_pop(self):
        """Test push and pop operations."""
        task1 = InitializationTask(plugin_type="plugin_a", config={}, priority=1)
        task2 = InitializationTask(plugin_type="plugin_b", config={}, priority=5)
        task3 = InitializationTask(plugin_type="plugin_c", config={}, priority=3)
        
        self.queue.push(task1)
        self.queue.push(task2)
        self.queue.push(task3)
        
        # Should pop in priority order (highest first)
        popped = self.queue.pop()
        self.assertEqual(popped.plugin_type, "plugin_b")
        
        popped = self.queue.pop()
        self.assertEqual(popped.plugin_type, "plugin_c")
        
        popped = self.queue.pop()
        self.assertEqual(popped.plugin_type, "plugin_a")

    def test_pop_empty_queue(self):
        """Test popping from empty queue."""
        result = self.queue.pop()
        self.assertIsNone(result)

    def test_peek(self):
        """Test peek operation."""
        task = InitializationTask(plugin_type="plugin_a", config={}, priority=5)
        self.queue.push(task)
        
        peeked = self.queue.peek()
        
        self.assertEqual(peeked.plugin_type, "plugin_a")
        self.assertEqual(self.queue.size(), 1)  # Still in queue

    def test_peek_empty_queue(self):
        """Test peeking empty queue."""
        result = self.queue.peek()
        self.assertIsNone(result)

    def test_is_empty(self):
        """Test is_empty check."""
        self.assertTrue(self.queue.is_empty())
        
        task = InitializationTask(plugin_type="plugin_a", config={})
        self.queue.push(task)
        
        self.assertFalse(self.queue.is_empty())

    def test_size(self):
        """Test size operation."""
        self.assertEqual(self.queue.size(), 0)
        
        for i in range(5):
            task = InitializationTask(plugin_type=f"plugin_{i}", config={})
            self.queue.push(task)
        
        self.assertEqual(self.queue.size(), 5)

    def test_clear(self):
        """Test clear operation."""
        for i in range(3):
            task = InitializationTask(plugin_type=f"plugin_{i}", config={})
            self.queue.push(task)
        
        self.queue.clear()
        
        self.assertEqual(self.queue.size(), 0)
        self.assertTrue(self.queue.is_empty())

    def test_fifo_order_same_priority(self):
        """Test FIFO order for same priority tasks."""
        task1 = InitializationTask(plugin_type="first", config={}, priority=5)
        task2 = InitializationTask(plugin_type="second", config={}, priority=5)
        task3 = InitializationTask(plugin_type="third", config={}, priority=5)
        
        self.queue.push(task1)
        self.queue.push(task2)
        self.queue.push(task3)
        
        self.assertEqual(self.queue.pop().plugin_type, "first")
        self.assertEqual(self.queue.pop().plugin_type, "second")
        self.assertEqual(self.queue.pop().plugin_type, "third")


class TestParallelInitializationScheduler(unittest.TestCase):
    """Test ParallelInitializationScheduler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.scheduler = ParallelInitializationScheduler(max_workers=4)

    def tearDown(self):
        """Clean up after tests."""
        self.scheduler.shutdown()

    def test_schedule_empty_tasks(self):
        """Test scheduling empty task list."""
        futures = self.scheduler.schedule([])
        
        self.assertEqual(futures, {})

    def test_schedule_single_task(self):
        """Test scheduling single task."""
        task = InitializationTask(
            plugin_type="plugin_a",
            config={"key": "value"},
        )
        
        futures = self.scheduler.schedule([task])
        
        self.assertIn("plugin_a", futures)

    def test_schedule_multiple_independent_tasks(self):
        """Test scheduling multiple independent tasks."""
        tasks = [
            InitializationTask(plugin_type="plugin_a", config={}),
            InitializationTask(plugin_type="plugin_b", config={}),
            InitializationTask(plugin_type="plugin_c", config={}),
        ]
        
        futures = self.scheduler.schedule(tasks)
        
        self.assertEqual(len(futures), 3)
        self.assertIn("plugin_a", futures)
        self.assertIn("plugin_b", futures)
        self.assertIn("plugin_c", futures)

    def test_schedule_with_dependencies(self):
        """Test scheduling tasks with dependencies."""
        tasks = [
            InitializationTask(
                plugin_type="plugin_a",
                config={},
                priority=1,
            ),
            InitializationTask(
                plugin_type="plugin_b",
                config={},
                dependencies=["plugin_a"],
                priority=2,
            ),
            InitializationTask(
                plugin_type="plugin_c",
                config={},
                dependencies=["plugin_a"],
                priority=3,
            ),
        ]
        
        futures = self.scheduler.schedule(tasks)
        
        self.assertEqual(len(futures), 3)

    def test_detect_circular_dependency(self):
        """Test detection of circular dependencies."""
        tasks = [
            InitializationTask(
                plugin_type="plugin_a",
                config={},
                dependencies=["plugin_c"],
            ),
            InitializationTask(
                plugin_type="plugin_b",
                config={},
                dependencies=["plugin_a"],
            ),
            InitializationTask(
                plugin_type="plugin_c",
                config={},
                dependencies=["plugin_b"],
            ),
        ]
        
        with self.assertRaises(ValueError) as context:
            self.scheduler.schedule(tasks)
        
        self.assertIn("Circular dependency", str(context.exception))

    def test_get_metrics(self):
        """Test getting metrics."""
        task = InitializationTask(plugin_type="plugin_a", config={})
        self.scheduler.schedule([task])
        
        metrics = self.scheduler.get_metrics()
        
        self.assertIsNotNone(metrics)
        self.assertIn("total_plugins", metrics)

    def test_shutdown(self):
        """Test shutdown operation."""
        task = InitializationTask(plugin_type="plugin_a", config={})
        self.scheduler.schedule([task])
        
        self.scheduler.shutdown()
        
        # After shutdown, scheduling should return empty
        futures = self.scheduler.schedule([
            InitializationTask(plugin_type="plugin_b", config={})
        ])
        
        self.assertEqual(futures, {})

    def test_schedule_after_shutdown(self):
        """Test scheduling after shutdown returns empty."""
        self.scheduler.shutdown()
        
        task = InitializationTask(plugin_type="plugin_a", config={})
        futures = self.scheduler.schedule([task])
        
        self.assertEqual(futures, {})


class TestParallelInitializationSchedulerThreadSafety(unittest.TestCase):
    """Test thread safety of ParallelInitializationScheduler."""

    def setUp(self):
        """Set up test fixtures."""
        self.scheduler = ParallelInitializationScheduler(max_workers=8)

    def tearDown(self):
        """Clean up after tests."""
        self.scheduler.shutdown()

    def test_concurrent_metrics_recording(self):
        """Test concurrent metrics recording."""
        metrics = InitializationMetrics()
        
        def record_worker(plugin_id):
            metrics.record_start(f"plugin_{plugin_id}")
            time.sleep(0.001)
            metrics.record_success(f"plugin_{plugin_id}")
        
        threads = [
            threading.Thread(target=record_worker, args=(i,))
            for i in range(10)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        summary = metrics.get_summary()
        
        self.assertEqual(summary["total_plugins"], 10)
        self.assertEqual(summary["successful"], 10)

    def test_concurrent_queue_operations(self):
        """Test concurrent queue operations."""
        queue = PriorityInitializationQueue()
        
        def push_worker(start_id):
            for i in range(10):
                task = InitializationTask(
                    plugin_type=f"plugin_{start_id}_{i}",
                    config={},
                )
                queue.push(task)
        
        threads = [
            threading.Thread(target=push_worker, args=(i,))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(queue.size(), 50)


if __name__ == "__main__":
    unittest.main()
