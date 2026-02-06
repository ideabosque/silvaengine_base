# Plugin Development Guide

## Overview

This guide introduces how to develop plugins for silvaengine_base. The PluginManager supports dynamic loading, parallel initialization, and comprehensive error handling mechanisms.

## Quick Start

### 1. Create a Plugin Module

Create a Python module and implement the `init(config)` function:

```python
# my_plugin.py
def init(config: dict) -> object:
    """
    Initialize plugin with configuration.
    
    Args:
        config: Plugin configuration dictionary
        
    Returns:
        Plugin manager instance
    """
    return MyPluginManager(config)


class MyPluginManager:
    def __init__(self, config: dict):
        self.config = config
    
    def get_status(self) -> dict:
        return {"status": "ok"}
```

### 2. Configure the Plugin

Add the plugin configuration to the configuration file:

```json
{
  "plugins": [
    {
      "type": "my_plugin",
      "config": {
        "setting1": "value1",
        "setting2": "value2"
      },
      "enabled": true,
      "module_name": "my_package.my_plugin",
      "function_name": "init"
    }
  ]
}
```

### 3. Use the Plugin

```python
from silvaengine_base import PluginManager

# Get singleton instance
manager = PluginManager()

# Initialize the plugin
manager.initialize({
    "plugins": [
        {
            "type": "my_plugin",
            "config": {...},
            "module_name": "my_package.my_plugin",
            "function_name": "init"
        }
    ]
})

# Get the plugin object
plugin = manager.get_initialized_object("my_plugin")
```

## Configuration Format Details

### Standard Format (Recommended)

```json
{
  "plugins": [
    {
      "type": "plugin_type",
      "config": {
        "key": "value"
      },
      "enabled": true,
      "module_name": "module.path",
      "class_name": "OptionalClass",
      "function_name": "init"
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | string | Yes | Plugin type identifier |
| config | dict | No | Plugin configuration (default: empty dict) |
| enabled | bool | No | Whether the plugin is enabled (default: true) |
| module_name | string | Yes | Python module path |
| class_name | string | No | Class name (for instantiation and method call) |
| function_name | string | No | Initialization function name (default: init) |

### Two Initialization Methods

**Method 1: Direct Function Call**

```python
# plugin_module.py
def init(config: dict) -> object:
    return PluginInstance(config)
```

Configuration:

```json
{
    "module_name": "plugin_module",
    "function_name": "init"
}
```

**Method 2: Instantiate Class Then Call Method**

```python
# plugin_module.py
class PluginClass:
    def init(self, config: dict) -> object:
        self.config = config
        return self
```

Configuration:

```json
{
  "module_name": "plugin_module",
  "class_name": "PluginClass",
  "function_name": "init"
}
```

## Advanced Features

### Parallel Initialization

When multiple plugins are configured, the system automatically initializes them in parallel to improve performance:

```python
manager.set_parallel_enabled(True)  # Enable parallel (default)
manager.set_max_workers(5)          # Set maximum concurrency
```

### Error Handling

Failure of a single plugin initialization does not affect other plugins:

```python
# Even if plugin1 fails, plugin2 will still be initialized
config = {
    "plugins": [
        {"type": "plugin1", ...},  # May fail
        {"type": "plugin2", ...}   # Will still execute
    ]
}
```

### Get Initialization Results

```python
# Get all plugin objects
all_objects = manager.get_initialized_objects()

# Get a specific plugin
my_plugin = manager.get_initialized_object("my_plugin")

# Get full context
context = manager.get_context()
```

## Complete Examples

### Example 1: Cache Plugin

```python
# cache_plugin.py
import redis

def init(config: dict) -> "CacheManager":
    return CacheManager(config)


class CacheManager:
    def __init__(self, config: dict):
        self.client = redis.Redis(
            host=config.get("host", "localhost"),
            port=config.get("port", 6379)
        )
    
    def get(self, key: str) -> str:
        return self.client.get(key)
    
    def set(self, key: str, value: str) -> bool:
        return self.client.set(key, value)
```

Configuration:

```json
{
  "plugins": [
    {
      "type": "cache",
      "config": {
        "host": "localhost",
        "port": 6379
      },
      "module_name": "my_plugins.cache_plugin",
      "function_name": "init"
    }
  ]
}
```

### Example 2: Multi-Plugin Configuration

```json
{
  "plugins": [
    {
      "type": "connection_pools",
      "config": {
        "postgresql": {
          "host": "localhost",
          "port": 5432,
          "database": "mydb"
        }
      },
      "module_name": "silvaengine_connections",
      "class_name": "PoolManager",
      "function_name": "init"
    },
    {
      "type": "cache",
      "config": {
        "host": "localhost",
        "port": 6379
      },
      "module_name": "my_plugins.cache_plugin",
      "function_name": "init"
    },
    {
      "type": "queue",
      "config": {
        "backend": "rabbitmq"
      },
      "module_name": "my_plugins.queue_plugin",
      "function_name": "init"
    }
  ]
}
```

## Best Practices

1. **Always implement the init function**: This is the entry point for the plugin
2. **Return a manageable object**: The init function should return a plugin manager instance
3. **Comprehensive error handling**: Handle exceptions within the plugin to avoid throwing uncaught exceptions
4. **Configuration validation**: Validate configuration parameters in the init function
5. **Logging**: Use logging to record the plugin initialization process
6. **Resource cleanup**: Implement appropriate shutdown methods (e.g., `shutdown()`)

## Backward Compatibility

The system supports the following legacy formats to ensure existing configurations continue to work:

- Use `resources` instead of `config`
- Nested format (e.g., `connection_pools: {...}`)

New plugins are recommended to use the standard format (`type` + `config`).
