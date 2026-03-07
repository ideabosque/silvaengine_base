#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Configuration validator for plugin management."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union


SENSITIVE_VALUE_MIN_LENGTH = 8
DEFAULT_PLUGIN_NAME_MIN_LENGTH = 1
DEFAULT_PLUGIN_NAME_MAX_LENGTH = 64


class ValidationSeverity(Enum):
    """Validation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    """Validation error data class."""
    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    code: str = ""


@dataclass
class ValidationResult:
    """Validation result data class."""
    is_valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def add_error(self, field: str, message: str, code: str = "") -> None:
        """Add an error to the result."""
        self.errors.append(
            ValidationError(
                field=field, message=message, severity=ValidationSeverity.ERROR, code=code
            )
        )
        self.is_valid = False

    def add_warning(self, field: str, message: str, code: str = "") -> None:
        """Add a warning to the result."""
        self.warnings.append(
            ValidationError(
                field=field, message=message, severity=ValidationSeverity.WARNING, code=code
            )
        )


class ConfigValidator:
    """Configuration validator for plugin system."""

    # Reserved keys that cannot be used as plugin names
    RESERVED_KEYS: Set[str] = {
        "config",
        "enabled",
        "module_name",
        "class_name",
        "function_name",
        "type",
        "dependencies",
        "version",
        "priority",
    }

    # Sensitive field patterns that should not be logged
    SENSITIVE_PATTERNS: List[str] = [
        r"password",
        r"secret",
        r"token",
        r"key",
        r"credential",
        r"auth",
    ]

    # Valid plugin name pattern
    PLUGIN_NAME_PATTERN: re.Pattern = re.compile(r"^[a-z][a-z0-9_]*$")

    def __init__(self):
        """Initialize the configuration validator."""
        self._validation_rules: Dict[str, Callable] = {}

    def validate_plugin_config(
        self, plugin_type: str, config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate a single plugin configuration."""
        result = ValidationResult()

        # Validate plugin type
        self._validate_plugin_type(plugin_type, result)

        # Validate configuration type
        if not isinstance(config, dict):
            result.add_error("", "Configuration must be a dictionary", "INVALID_TYPE")
            return result

        # Validate required fields
        self._validate_required_fields(config, result)

        # Validate field types
        self._validate_field_types(config, result)

        # Validate plugin name
        if plugin_type:
            self._validate_plugin_name(plugin_type, result)

        # Validate dependencies
        self._validate_dependencies(config, result)

        # Validate module_name format
        self._validate_module_name(config.get("module_name"), result)

        # Validate function_name format
        self._validate_function_name(config.get("function_name"), result)

        # Validate class_name format if present
        if config.get("class_name"):
            self._validate_class_name(config.get("class_name"), result)

        # Security validation
        self._validate_security(config, result)

        return result

    def validate_plugins_config(
        self, plugins_config: List[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate the entire plugins configuration list."""
        result = ValidationResult()

        if not isinstance(plugins_config, list):
            result.add_error(
                "plugins", "Plugins configuration must be a list", "INVALID_TYPE"
            )
            return result

        if not plugins_config:
            result.add_warning("plugins", "Empty plugins configuration", "EMPTY_CONFIG")
            return result

        # Track plugin names for duplicate detection
        plugin_names: Set[str] = set()

        for index, plugin_item in enumerate(plugins_config):
            if not isinstance(plugin_item, dict):
                result.add_error(
                    f"plugins[{index}]",
                    f"Plugin item at index {index} must be a dictionary",
                    "INVALID_TYPE",
                )
                continue

            # Extract plugin type
            plugin_type = plugin_item.get("type", "").strip().lower()

            if not plugin_type:
                result.add_error(
                    f"plugins[{index}].type",
                    f"Plugin type is required at index {index}",
                    "MISSING_TYPE",
                )
                continue

            # Check for duplicate plugin names
            if plugin_type in plugin_names:
                result.add_error(
                    f"plugins[{index}].type",
                    f"Duplicate plugin type: {plugin_type}",
                    "DUPLICATE_PLUGIN",
                )
            else:
                plugin_names.add(plugin_type)

            # Validate individual plugin configuration
            plugin_result = self.validate_plugin_config(plugin_type, plugin_item)

            # Merge results
            for error in plugin_result.errors:
                result.add_error(
                    f"plugins[{index}].{error.field}", error.message, error.code
                )

            for warning in plugin_result.warnings:
                result.add_warning(
                    f"plugins[{index}].{warning.field}", warning.message, warning.code
                )

        # Validate cross-plugin dependencies
        self._validate_cross_plugin_dependencies(plugins_config, result)

        return result

    def _validate_plugin_type(self, plugin_type: str, result: ValidationResult) -> None:
        """Validate plugin type identifier."""
        if not plugin_type:
            result.add_error("type", "Plugin type is required", "MISSING_TYPE")
            return

        if not isinstance(plugin_type, str):
            result.add_error("type", "Plugin type must be a string", "INVALID_TYPE")
            return

        if not self.PLUGIN_NAME_PATTERN.match(plugin_type):
            result.add_error(
                "type",
                "Plugin type must start with a letter and contain only lowercase letters, numbers, and underscores",
                "INVALID_FORMAT",
            )

    def _validate_required_fields(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate required fields are present."""
        required_fields = ["module_name"]

        for field in required_fields:
            if field not in config or not config[field]:
                result.add_error(field, f"Required field '{field}' is missing", "MISSING_FIELD")

    def _validate_field_types(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate field types."""
        type_validations = {
            "enabled": bool,
            "module_name": str,
            "function_name": str,
            "dependencies": list,
        }

        for field, expected_type in type_validations.items():
            if field in config and config[field] is not None:
                if not isinstance(config[field], expected_type):
                    result.add_error(
                        field,
                        f"Field '{field}' must be of type {expected_type.__name__}",
                        "INVALID_TYPE",
                    )

        # Validate class_name can be string or None
        if "class_name" in config:
            class_name = config["class_name"]
            if class_name is not None and not isinstance(class_name, str):
                result.add_error(
                    "class_name",
                    "Field 'class_name' must be a string or null",
                    "INVALID_TYPE",
                )

    def _validate_plugin_name(self, plugin_name: str, result: ValidationResult) -> None:
        """Validate plugin name."""
        if plugin_name in self.RESERVED_KEYS:
            result.add_error(
                "type",
                f"Plugin type '{plugin_name}' is a reserved keyword",
                "RESERVED_NAME",
            )

    def _validate_dependencies(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate dependencies configuration."""
        dependencies = config.get("dependencies", [])

        if dependencies is None:
            return

        if not isinstance(dependencies, list):
            result.add_error(
                "dependencies", "Dependencies must be a list", "INVALID_TYPE"
            )
            return

        for index, dep in enumerate(dependencies):
            if not isinstance(dep, str):
                result.add_error(
                    f"dependencies[{index}]",
                    f"Dependency at index {index} must be a string",
                    "INVALID_TYPE",
                )
                continue

            if not dep.strip():
                result.add_error(
                    f"dependencies[{index}]",
                    f"Dependency at index {index} cannot be empty",
                    "EMPTY_DEPENDENCY",
                )
                continue

            if not self.PLUGIN_NAME_PATTERN.match(dep):
                result.add_error(
                    f"dependencies[{index}]",
                    f"Dependency '{dep}' has invalid format",
                    "INVALID_FORMAT",
                )

    def _validate_module_name(
        self, module_name: Any, result: ValidationResult
    ) -> None:
        """Validate module name format."""
        if not module_name:
            return

        if not isinstance(module_name, str):
            return

        # Check for invalid characters
        if " " in module_name:
            result.add_error(
                "module_name", "Module name cannot contain spaces", "INVALID_FORMAT"
            )

        # Check for valid Python module format
        if module_name.startswith(".") or module_name.endswith("."):
            result.add_error(
                "module_name",
                "Module name cannot start or end with a dot",
                "INVALID_FORMAT",
            )

        # Check for consecutive dots
        if ".." in module_name:
            result.add_error(
                "module_name",
                "Module name cannot contain consecutive dots",
                "INVALID_FORMAT",
            )

    def _validate_function_name(
        self, function_name: Any, result: ValidationResult
    ) -> None:
        """Validate function name format."""
        if not function_name:
            return

        if not isinstance(function_name, str):
            return

        # Check for valid Python identifier
        if not function_name.isidentifier():
            result.add_error(
                "function_name",
                "Function name must be a valid Python identifier",
                "INVALID_FORMAT",
            )

    def _validate_class_name(
        self, class_name: Any, result: ValidationResult
    ) -> None:
        """Validate class name format."""
        if not class_name:
            return

        if not isinstance(class_name, str):
            return

        # Check for valid Python class name (CamelCase)
        if not class_name[0].isupper():
            result.add_warning(
                "class_name",
                "Class name should start with an uppercase letter",
                "NAMING_CONVENTION",
            )

        if not class_name.isidentifier():
            result.add_error(
                "class_name",
                "Class name must be a valid Python identifier",
                "INVALID_FORMAT",
            )

    def _validate_security(
        self, config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate security-related configuration."""
        # Check for hardcoded secrets in config
        self._check_for_hardcoded_secrets(config, "", result)

    def _check_for_hardcoded_secrets(
        self, config: Dict[str, Any], path: str, result: ValidationResult
    ) -> None:
        """Recursively check for hardcoded secrets."""
        if not isinstance(config, dict):
            return

        for key, value in config.items():
            current_path = f"{path}.{key}" if path else key

            # Check if key matches sensitive patterns
            is_sensitive = any(
                re.search(pattern, key, re.IGNORECASE)
                for pattern in self.SENSITIVE_PATTERNS
            )

            if is_sensitive and isinstance(value, str) and value:
                # Check if value looks like a hardcoded secret
                if len(value) > SENSITIVE_VALUE_MIN_LENGTH and not value.startswith("$"):
                    result.add_warning(
                        current_path,
                        f"Field '{key}' may contain a hardcoded secret. Consider using environment variables",
                        "HARDCODED_SECRET",
                    )

            # Recursively check nested dictionaries
            if isinstance(value, dict):
                self._check_for_hardcoded_secrets(value, current_path, result)

    def _validate_cross_plugin_dependencies(
        self, plugins_config: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate dependencies across all plugins."""
        # Build plugin name set
        plugin_names: Set[str] = set()
        for plugin in plugins_config:
            if isinstance(plugin, dict):
                plugin_type = plugin.get("type", "").strip().lower()
                if plugin_type:
                    plugin_names.add(plugin_type)

        # Check for missing dependencies
        for plugin in plugins_config:
            if not isinstance(plugin, dict):
                continue

            plugin_type = plugin.get("type", "").strip().lower()
            dependencies = plugin.get("dependencies", [])

            if not isinstance(dependencies, list):
                continue

            for dep in dependencies:
                if isinstance(dep, str):
                    dep_name = dep.strip().lower()
                    if dep_name and dep_name not in plugin_names:
                        result.add_error(
                            f"{plugin_type}.dependencies",
                            f"Dependency '{dep_name}' is not defined in any plugin",
                            "MISSING_DEPENDENCY",
                        )

    def register_validation_rule(
        self, field: str, validator: Callable
    ) -> None:
        """Register a custom validation rule."""
        self._validation_rules[field] = validator


# Global validator instance
_config_validator: Optional[ConfigValidator] = None


def get_config_validator() -> ConfigValidator:
    """Get the global configuration validator instance."""
    global _config_validator
    if _config_validator is None:
        _config_validator = ConfigValidator()
    return _config_validator
