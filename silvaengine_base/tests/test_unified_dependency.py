#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified Dependency Resolver tests.

This module tests the UnifiedDependencyResolver class for:
- Circular dependency detection
- Topological sorting
- Dependency validation
- Edge cases and error handling

@since 2.0.0
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock

mock_invoker_module = MagicMock()
mock_invoker_module.Invoker = MagicMock()
sys.modules['silvaengine_utility'] = mock_invoker_module

mock_dynamodb_module = MagicMock()
sys.modules['silvaengine_dynamodb_base'] = mock_dynamodb_module
sys.modules['silvaengine_dynamodb_base.models'] = MagicMock()

mock_constants_module = MagicMock()
sys.modules['silvaengine_constants'] = mock_constants_module

import unittest
from unittest.mock import MagicMock, patch

from silvaengine_base.boosters.plugin.dependency import UnifiedDependencyResolver


class TestUnifiedDependencyResolverDetectCycle(unittest.TestCase):
    """Test circular dependency detection."""

    def test_no_cycle_simple(self):
        """Test detection with no cycle - simple case."""
        nodes = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNone(result)

    def test_no_cycle_complex(self):
        """Test detection with no cycle - complex case."""
        nodes = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D"],
            "D": ["E"],
            "E": [],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNone(result)

    def test_simple_cycle(self):
        """Test detection of simple cycle A -> B -> A."""
        nodes = {
            "A": ["B"],
            "B": ["A"],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNotNone(result)
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_self_cycle(self):
        """Test detection of self-referential cycle A -> A."""
        nodes = {
            "A": ["A"],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNotNone(result)
        self.assertEqual(result, ["A", "A"])

    def test_longer_cycle(self):
        """Test detection of longer cycle A -> B -> C -> A."""
        nodes = {
            "A": ["B"],
            "B": ["C"],
            "C": ["A"],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)

    def test_empty_graph(self):
        """Test detection with empty graph."""
        nodes = {}
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNone(result)

    def test_single_node_no_deps(self):
        """Test detection with single node, no dependencies."""
        nodes = {
            "A": [],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNone(result)

    def test_disconnected_graph_no_cycle(self):
        """Test detection with disconnected graph, no cycles."""
        nodes = {
            "A": [],
            "B": [],
            "C": [],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNone(result)

    def test_disconnected_graph_with_cycle(self):
        """Test detection with disconnected graph, one component has cycle."""
        nodes = {
            "A": [],
            "B": ["C"],
            "C": ["B"],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes)
        self.assertIsNotNone(result)


class TestUnifiedDependencyResolverTopologicalSort(unittest.TestCase):
    """Test topological sorting."""

    def test_simple_sort(self):
        """Test simple topological sort."""
        nodes = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 3)
        self.assertLess(result.index("C"), result.index("B"))
        self.assertLess(result.index("B"), result.index("A"))

    def test_complex_sort(self):
        """Test complex topological sort with multiple dependencies."""
        nodes = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D"],
            "D": ["E"],
            "E": [],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 5)
        self.assertLess(result.index("E"), result.index("D"))
        self.assertLess(result.index("D"), result.index("B"))
        self.assertLess(result.index("D"), result.index("C"))
        self.assertLess(result.index("B"), result.index("A"))
        self.assertLess(result.index("C"), result.index("A"))

    def test_empty_graph_sort(self):
        """Test sorting empty graph."""
        nodes = {}
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(result, [])

    def test_single_node_sort(self):
        """Test sorting single node."""
        nodes = {
            "A": [],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(result, ["A"])

    def test_disconnected_graph_sort(self):
        """Test sorting disconnected graph."""
        nodes = {
            "A": [],
            "B": [],
            "C": [],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 3)
        self.assertIn("A", result)
        self.assertIn("B", result)
        self.assertIn("C", result)

    def test_cycle_detection_in_sort(self):
        """Test that sort detects cycles."""
        nodes = {
            "A": ["B"],
            "B": ["A"],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertFalse(success)

    def test_missing_dependency_in_sort(self):
        """Test sorting with missing dependency (referenced but not defined)."""
        nodes = {
            "A": ["B"],
            "B": ["C"],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 2)


class TestUnifiedDependencyResolverValidateDependencies(unittest.TestCase):
    """Test dependency validation."""

    def test_all_dependencies_present(self):
        """Test validation when all dependencies are present."""
        nodes = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }
        
        result = UnifiedDependencyResolver.validate_dependencies(nodes)
        
        self.assertEqual(result, {})

    def test_missing_dependency(self):
        """Test validation with missing dependency."""
        nodes = {
            "A": ["B"],
            "B": ["MISSING"],
        }
        
        result = UnifiedDependencyResolver.validate_dependencies(nodes)
        
        self.assertIn("B", result)
        self.assertIn("MISSING", result["B"])

    def test_multiple_missing_dependencies(self):
        """Test validation with multiple missing dependencies."""
        nodes = {
            "A": ["MISSING1", "MISSING2"],
            "B": ["MISSING3"],
        }
        
        result = UnifiedDependencyResolver.validate_dependencies(nodes)
        
        self.assertIn("A", result)
        self.assertIn("MISSING1", result["A"])
        self.assertIn("MISSING2", result["A"])
        self.assertIn("B", result)
        self.assertIn("MISSING3", result["B"])

    def test_empty_graph_validation(self):
        """Test validation of empty graph."""
        nodes = {}
        
        result = UnifiedDependencyResolver.validate_dependencies(nodes)
        
        self.assertEqual(result, {})

    def test_no_dependencies_validation(self):
        """Test validation of nodes with no dependencies."""
        nodes = {
            "A": [],
            "B": [],
            "C": [],
        }
        
        result = UnifiedDependencyResolver.validate_dependencies(nodes)
        
        self.assertEqual(result, {})


class TestUnifiedDependencyResolverEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_large_graph(self):
        """Test with a large dependency graph."""
        nodes = {f"plugin_{i}": [f"plugin_{i-1}"] if i > 0 else [] for i in range(100)}
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 100)
        self.assertEqual(result[0], "plugin_0")
        self.assertEqual(result[-1], "plugin_99")

    def test_wide_graph(self):
        """Test with a wide dependency graph."""
        nodes = {
            "root": [],
            **{f"child_{i}": ["root"] for i in range(50)},
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 51)
        self.assertEqual(result[0], "root")

    def test_diamond_dependency(self):
        """Test diamond dependency pattern."""
        nodes = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D"],
            "D": [],
        }
        
        success, result = UnifiedDependencyResolver.topological_sort(nodes)
        
        self.assertTrue(success)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], "D")

    def test_with_logger(self):
        """Test with logger parameter."""
        mock_logger = MagicMock()
        
        nodes = {
            "A": ["B"],
            "B": [],
        }
        
        result = UnifiedDependencyResolver.detect_cycle(nodes, mock_logger)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
