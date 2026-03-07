#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for ConfigValidator module.

Tests cover:
- Plugin type validation
- Required field validation
- Field type validation
- Dependency validation
- Security validation
- Cross-plugin dependency validation
"""

import unittest
from typing import Any, Dict

import sys
sys.path.insert(0, "/Users/Garabateador/Workspace/abacusipllc/backend/gpt/silvaengine_base")

from silvaengine_base.boosters.plugin.config_validator import (
    ConfigValidator,
    ValidationSeverity,
    ValidationResult,
    ValidationError,
    get_config_validator,
)


class TestValidationResult(unittest.TestCase):
    """Test ValidationResult dataclass."""

    def test_initial_state(self):
        """Test initial state is valid with empty errors."""
        result = ValidationResult()
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)

    def test_add_error(self):
        """Test adding error marks result as invalid."""
        result = ValidationResult()
        result.add_error("field1", "Error message", "ERROR_CODE")
        
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].field, "field1")
        self.assertEqual(result.errors[0].message, "Error message")
        self.assertEqual(result.errors[0].code, "ERROR_CODE")

    def test_add_warning(self):
        """Test adding warning does not mark result as invalid."""
        result = ValidationResult()
        result.add_warning("field1", "Warning message", "WARNING_CODE")
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.warnings), 1)


class TestConfigValidator(unittest.TestCase):
    """Test ConfigValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = ConfigValidator()

    def test_validate_valid_plugin_config(self):
        """Test validation of a valid plugin configuration."""
        config = {
            "module_name": "test_module",
            "function_name": "init",
            "dependencies": ["dep1", "dep2"],
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertTrue(result.is_valid)

    def test_validate_missing_module_name(self):
        """Test validation fails when module_name is missing."""
        config = {
            "function_name": "init",
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "MISSING_FIELD" for e in result.errors))

    def test_validate_invalid_plugin_type(self):
        """Test validation fails for invalid plugin type."""
        config = {"module_name": "test_module"}
        
        # Test empty type
        result = self.validator.validate_plugin_config("", config)
        self.assertFalse(result.is_valid)
        
        # Test type starting with number
        result = self.validator.validate_plugin_config("123_plugin", config)
        self.assertFalse(result.is_valid)
        
        # Test type with spaces
        result = self.validator.validate_plugin_config("test plugin", config)
        self.assertFalse(result.is_valid)

    def test_validate_reserved_plugin_type(self):
        """Test validation fails for reserved plugin types."""
        config = {"module_name": "test_module"}
        
        for reserved in ["config", "enabled", "type"]:
            result = self.validator.validate_plugin_config(reserved, config)
            self.assertFalse(result.is_valid)
            self.assertTrue(any(e.code == "RESERVED_NAME" for e in result.errors))

    def test_validate_invalid_dependencies(self):
        """Test validation of invalid dependencies."""
        config = {
            "module_name": "test_module",
            "dependencies": "not_a_list",  # Should be a list
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "INVALID_TYPE" for e in result.errors))

    def test_validate_empty_dependency(self):
        """Test validation fails for empty dependency."""
        config = {
            "module_name": "test_module",
            "dependencies": [""],  # Empty dependency
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "EMPTY_DEPENDENCY" for e in result.errors))

    def test_validate_invalid_module_name(self):
        """Test validation of invalid module names."""
        # Module name with spaces
        config = {"module_name": "test module"}
        result = self.validator.validate_plugin_config("test_plugin", config)
        self.assertTrue(any(e.code == "INVALID_FORMAT" for e in result.errors))
        
        # Module name starting with dot
        config = {"module_name": ".test_module"}
        result = self.validator.validate_plugin_config("test_plugin", config)
        self.assertTrue(any(e.code == "INVALID_FORMAT" for e in result.errors))
        
        # Module name with consecutive dots
        config = {"module_name": "test..module"}
        result = self.validator.validate_plugin_config("test_plugin", config)
        self.assertTrue(any(e.code == "INVALID_FORMAT" for e in result.errors))

    def test_validate_invalid_function_name(self):
        """Test validation of invalid function names."""
        config = {
            "module_name": "test_module",
            "function_name": "123_invalid",  # Cannot start with number
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertTrue(any(e.code == "INVALID_FORMAT" for e in result.errors))

    def test_validate_class_name_naming_convention(self):
        """Test warning for class name not following naming convention."""
        config = {
            "module_name": "test_module",
            "class_name": "lowercase_class",  # Should start with uppercase
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertTrue(any(w.code == "NAMING_CONVENTION" for w in result.warnings))


class TestValidatePluginsConfig(unittest.TestCase):
    """Test validate_plugins_config method."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = ConfigValidator()

    def test_validate_valid_plugins_list(self):
        """Test validation of a valid plugins list."""
        plugins = [
            {
                "type": "plugin_a",
                "module_name": "module_a",
                "function_name": "init",
            },
            {
                "type": "plugin_b",
                "module_name": "module_b",
                "function_name": "init",
                "dependencies": ["plugin_a"],
            },
        ]
        result = self.validator.validate_plugins_config(plugins)
        
        self.assertTrue(result.is_valid)

    def test_validate_empty_plugins_list(self):
        """Test validation of empty plugins list."""
        result = self.validator.validate_plugins_config([])
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.warnings), 1)

    def test_validate_invalid_plugins_type(self):
        """Test validation fails for non-list plugins."""
        result = self.validator.validate_plugins_config("not_a_list")
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "INVALID_TYPE" for e in result.errors))

    def test_validate_duplicate_plugin_type(self):
        """Test validation fails for duplicate plugin types."""
        plugins = [
            {"type": "plugin_a", "module_name": "module_a"},
            {"type": "plugin_a", "module_name": "module_b"},  # Duplicate
        ]
        result = self.validator.validate_plugins_config(plugins)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "DUPLICATE_PLUGIN" for e in result.errors))

    def test_validate_missing_dependency(self):
        """Test validation fails for missing dependency."""
        plugins = [
            {
                "type": "plugin_a",
                "module_name": "module_a",
                "dependencies": ["non_existent_plugin"],
            },
        ]
        result = self.validator.validate_plugins_config(plugins)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any(e.code == "MISSING_DEPENDENCY" for e in result.errors))


class TestSecurityValidation(unittest.TestCase):
    """Test security-related validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = ConfigValidator()

    def test_hardcoded_password_warning(self):
        """Test warning for hardcoded password."""
        config = {
            "module_name": "test_module",
            "password": "hardcoded_secret_value",  # Hardcoded secret
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertTrue(any(w.code == "HARDCODED_SECRET" for w in result.warnings))

    def test_env_var_reference_no_warning(self):
        """Test no warning for environment variable reference."""
        config = {
            "module_name": "test_module",
            "password": "$ENV_PASSWORD",  # Environment variable reference
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertFalse(any(w.code == "HARDCODED_SECRET" for w in result.warnings))

    def test_short_secret_no_warning(self):
        """Test no warning for short secret values."""
        config = {
            "module_name": "test_module",
            "password": "short",  # Too short to be a real secret
        }
        result = self.validator.validate_plugin_config("test_plugin", config)
        
        self.assertFalse(any(w.code == "HARDCODED_SECRET" for w in result.warnings))


class TestGetConfigValidator(unittest.TestCase):
    """Test get_config_validator function."""

    def test_singleton_instance(self):
        """Test that get_config_validator returns a singleton."""
        validator1 = get_config_validator()
        validator2 = get_config_validator()
        
        self.assertIs(validator1, validator2)


if __name__ == "__main__":
    unittest.main()
