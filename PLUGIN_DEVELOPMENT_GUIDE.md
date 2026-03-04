# SilvaEngine 插件开发指南

## 概述

SilvaEngine Base 是一个为 AWS Lambda 设计的事件驱动框架，提供了完整的插件系统、事件处理路由和资源管理功能。本指南详细介绍了如何为 silvaengine_base 开发插件，以及框架的核心架构和最佳实践。

## 目录

1. [架构概览](#架构概览)
2. [核心组件详解](#核心组件详解)
3. [快速开始](#快速开始)
4. [插件配置格式](#插件配置格式)
5. [核心 API 参考](#核心-api-参考)
6. [配置验证](#配置验证)
7. [插件生命周期管理](#插件生命周期管理)
8. [高级特性](#高级特性)
9. [事件处理器开发](#事件处理器开发)
10. [最佳实践](#最佳实践)
11. [完整示例](#完整示例)
12. [故障排除](#故障排除)
13. [向后兼容性](#向后兼容性)

---

## 架构概览

### 目录结构

```
silvaengine_base/
├── silvaengine_base/
│   ├── boosters/
│   │   └── plugin/
│   │       ├── __init__.py          # PluginManager 主入口
│   │       ├── context.py           # PluginContext 上下文管理
│   │       ├── injector.py          # PluginContextInjector 上下文注入器
│   │       ├── dependency.py        # DependencyResolver 依赖解析
│   │       ├── circuit_breaker.py   # CircuitBreaker 熔断器
│   │       ├── config_validator.py  # ConfigValidator 配置验证
│   │       └── lazy_context.py      # LazyPluginContext 延迟加载
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── default.py               # DefaultHandler 默认处理器
│   │   ├── http.py                  # HttpHandler HTTP请求处理
│   │   ├── websocket.py             # WebSocketHandler WebSocket处理
│   │   ├── lambda.py                # LambdaInvocationHandler Lambda调用
│   │   ├── dynamodb.py              # DynamodbHandler DynamoDB流
│   │   ├── s3.py                    # S3Handler S3事件
│   │   ├── sqs.py                   # SQSHandler SQS消息
│   │   ├── sns.py                   # SNSHandler SNS通知
│   │   ├── event_bridge.py          # EventBridgeHandler EventBridge
│   │   ├── cloudwatch.py            # CloudwatchLogHandler CloudWatch日志
│   │   ├── cognito.py               # CognitoHandler Cognito触发器
│   │   └── bot.py                   # BotHandler Bot处理
│   ├── __init__.py                  # 模块导出
│   ├── handler.py                   # Handler 基类
│   └── resources.py                 # Resources 资源管理
├── config.schema.json               # JSON Schema配置验证
├── setup.py                         # 包安装配置
├── Pipfile                          # 依赖管理
├── README.md                        # 项目说明
├── PLUGIN_DEVELOPMENT_GUIDE.md      # 插件开发指南
└── LICENSE                          # 许可证
```

### 核心架构流程

```
AWS Lambda Event
       ↓
   Resources
       ↓
  Event Router (匹配对应的 Handler)
       ↓
  PluginManager (初始化插件)
       ↓
  PluginContextInjector (注入上下文)
       ↓
   Handler.handle() (处理事件)
       ↓
   Business Logic (业务逻辑)
```

### 模块依赖关系

```
Resources
    ├── Handler (基类)
    ├── PluginManager
    │   ├── ConfigValidator
    │   ├── DependencyResolver
    │   ├── CircuitBreaker
    │   └── LazyPluginContext
    ├── PluginContextInjector
    └── EventHandlers
        ├── HttpHandler
        ├── WebSocketHandler
        ├── LambdaInvocationHandler
        ├── DynamodbHandler
        ├── S3Handler
        ├── SQSHandler
        ├── SNSHandler
        ├── EventBridgeHandler
        ├── CloudwatchLogHandler
        ├── CognitoHandler
        ├── BotHandler
        └── DefaultHandler
```

---

## 核心组件详解

### 1. Handler 基类

Handler 是所有事件处理器的基类，提供了丰富的事件处理辅助方法。

**核心功能：**

- 事件参数提取（endpoint_id, api_key, area 等）
- 授权和权限验证
- Lambda 函数调用
- 配置管理
- 插件上下文注入

**关键属性：**

```python
class Handler:
    region = os.getenv("REGION_NAME", "us-east-1")
    aws_lambda = boto3.client("lambda", region_name=region)
    plugin_context = PluginContextDescriptor()  # 描述符实现上下文注入
```

**核心方法：**

| 方法 | 描述 |
|------|------|
| `handle()` | 处理事件（子类必须实现） |
| `is_event_match_handler(event)` | 判断事件是否匹配（类方法） |
| `_extract_core_parameters()` | 提取核心参数（api_key, endpoint_id, parameters） |
| `_get_function_and_setting()` | 获取函数配置和设置 |
| `_invoke_authorization(action)` | 调用授权函数 |
| `_get_proxied_callable()` | 获取可调用的代理对象 |
| `set_plugin_context(context)` | 设置插件上下文 |
| `get_plugin_context()` | 获取插件上下文 |

### 2. Resources 类

Resources 是 Lambda 事件处理的主入口，负责事件路由和插件初始化。

**核心职责：**

- 事件路由到对应的 Handler
- 插件系统初始化
- PluginManager 配置管理
- 错误处理和响应格式化

**初始化参数：**

```python
Resources(
    logger,                          # 日志记录器
    plugin_init_timeout=30.0,        # 单个插件初始化超时
    global_init_timeout=120.0,       # 全局初始化超时
    circuit_breaker_enabled=True,    # 熔断器开关
    lazy_loading_enabled=False,      # 延迟加载开关
    parallel_enabled=True,           # 并行初始化开关
    max_workers=None,                # 最大工作线程数
)
```

**使用示例：**

```python
import logging
from silvaengine_base import Resources

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建 Resources 实例
resources = Resources(
    logger=logger,
    plugin_init_timeout=30.0,
    global_init_timeout=120.0,
    circuit_breaker_enabled=True,
    lazy_loading_enabled=False,
)

# 获取 Lambda handler
lambda_handler = resources.get_handler()

# 在 Lambda 中使用
def lambda_handler(event, context):
    return resources.handle(event, context)
```

### 3. PluginManager

PluginManager 是插件系统的核心，负责插件的注册、初始化和生命周期管理。

**设计模式：**

- 单例模式（确保全局唯一实例）
- 工厂模式（动态创建插件实例）
- 策略模式（支持不同的初始化策略）

**核心特性：**

1. **并行初始化**: 使用 ThreadPoolExecutor 并行初始化多个插件
2. **依赖解析**: 使用拓扑排序确保正确的初始化顺序
3. **熔断器**: 防止故障插件反复失败
4. **延迟加载**: 按需初始化插件，优化冷启动
5. **配置验证**: 初始化前验证配置的正确性

**配置选项：**

```python
manager = PluginManager(logger=logger)

# 设置超时
manager.set_plugin_init_timeout(30.0)      # 单个插件超时
manager.set_global_init_timeout(120.0)     # 全局超时

# 启用特性
manager.set_parallel_enabled(True)          # 并行初始化
manager.set_circuit_breaker_enabled(True)   # 熔断器
manager.set_lazy_loading_enabled(False)     # 延迟加载
manager.set_max_workers(8)                  # 最大工作线程

# 验证模式
manager.set_validation_strict_mode(True)    # 严格验证模式
```

### 4. PluginContext

PluginContext 提供线程安全的插件访问机制。

**核心功能：**

- 线程安全的插件获取
- 等待插件初始化完成
- 获取所有已初始化插件
- 查询插件状态

**使用示例：**

```python
from silvaengine_base import PluginManager, PluginContext

manager = PluginManager()
manager.initialize(setting)

# 获取上下文
context = manager.get_context()

# 使用上下文管理器
with context as ctx:
    plugin = ctx.get("my_plugin")
    if plugin:
        result = plugin.do_something()

# 或直接获取
plugin = context.get("my_plugin")

# 获取或抛出异常
try:
    plugin = context.get_or_raise("my_plugin")
except PluginNotFoundError:
    logger.error("Plugin not found")

# 等待插件初始化
if context.wait_for_plugin("my_plugin", timeout=30.0):
    plugin = context.get("my_plugin")
```

### 5. PluginContextInjector

PluginContextInjector 实现线程本地存储的上下文注入，允许在函数调用链中自动传递插件上下文。

**核心机制：**

- 使用 `threading.local()` 实现线程隔离
- 支持嵌套上下文管理
- 通过描述符实现自动注入

**使用示例：**

```python
from silvaengine_base import (
    PluginContextInjector,
    get_current_plugin_context,
    inject_plugin_context,
)

# 方式一：使用上下文管理器
with PluginContextInjector(plugin_context):
    # 在此范围内可以访问插件上下文
    context = get_current_plugin_context()
    plugin = context.get("my_plugin")

# 方式二：使用装饰器风格的上下文管理器
@inject_plugin_context(plugin_context)
def my_function():
    context = get_current_plugin_context()
    return context.get("my_plugin")

# 方式三：在 Handler 中使用描述符
class MyHandler(Handler):
    plugin_context = PluginContextDescriptor()
    
    def handle(self):
        # 直接访问 self.plugin_context
        plugin = self.plugin_context.get("my_plugin")
```

### 6. CircuitBreaker

CircuitBreaker 实现熔断器模式，防止故障插件反复失败影响系统稳定性。

**三种状态：**

```
CLOSED (正常) → OPEN (熔断) → HALF_OPEN (半开) → CLOSED
     ↑                                          ↓
     └──────────── 失败次数超过阈值 ─────────────┘
```

**状态说明：**

| 状态 | 描述 |
|------|------|
| CLOSED | 正常状态，允许调用 |
| OPEN | 熔断状态，拒绝调用，等待恢复 |
| HALF_OPEN | 半开状态，允许有限次数的测试调用 |

**配置参数：**

```python
from silvaengine_base import CircuitBreaker, get_circuit_breaker_registry

# 获取熔断器注册表
registry = get_circuit_breaker_registry()

# 创建或获取熔断器
circuit_breaker = registry.get_or_create(
    name="my_plugin",
    failure_threshold=3,      # 失败阈值
    recovery_timeout=60.0,    # 恢复超时（秒）
)

# 使用熔断器
try:
    result = circuit_breaker.call(my_function, arg1, arg2)
except Exception as e:
    logger.error(f"Circuit breaker blocked or function failed: {e}")

# 获取统计信息
stats = circuit_breaker.get_stats()
print(f"State: {stats['state']}")
print(f"Failures: {stats['failure_count']}")

# 重置熔断器
circuit_breaker.reset()
```

### 7. LazyPluginContext

LazyPluginContext 实现按需初始化插件，优化 Lambda 冷启动性能。

**工作原理：**

1. 初始化时只存储插件配置，不实际初始化
2. 第一次访问插件时才进行初始化
3. 初始化结果被缓存，后续访问直接返回

**使用场景：**

- Lambda 冷启动优化
- 减少不必要的插件初始化
- 按需加载资源密集型插件

**配置示例：**

```python
from silvaengine_base import PluginManager

manager = PluginManager()
manager.set_lazy_loading_enabled(True)

# 初始化时不会立即加载插件
manager.initialize(setting)

# 第一次访问时才初始化
plugin = manager.get_initialized_object("my_plugin")

# 获取延迟加载统计
stats = manager.get_all_plugin_status()
print(stats["lazy_loading_stats"])
```

### 8. DependencyResolver

DependencyResolver 负责解析插件依赖关系，确保正确的初始化顺序。

**核心功能：**

- 拓扑排序确定初始化顺序
- 检测循环依赖
- 验证依赖是否存在

**使用示例：**

```python
from silvaengine_base.boosters.plugin.dependency import (
    DependencyResolver,
    PluginDependency,
)

resolver = DependencyResolver()

# 定义插件依赖
plugins = [
    PluginDependency(plugin_name="database", dependencies=[]),
    PluginDependency(plugin_name="cache", dependencies=["database"]),
    PluginDependency(plugin_name="api", dependencies=["cache", "database"]),
]

# 解析依赖顺序
resolved_order = resolver.resolve_dependencies(plugins)
# 结果: [database, cache, api]

# 检测循环依赖
circular = resolver.detect_circular_dependencies(plugins)
if circular:
    print(f"Circular dependency detected: {' -> '.join(circular)}")

# 验证依赖
missing = resolver.validate_dependencies(plugins)
if missing:
    print(f"Missing dependencies: {missing}")
```

### 9. ConfigValidator

ConfigValidator 提供完整的配置验证功能，在初始化前检测配置错误。

**验证规则：**

1. 必需字段检查（`type`, `module_name`）
2. 类型检查（`enabled` 必须是布尔值等）
3. 格式验证（插件类型命名规范）
4. 保留关键字检查
5. 依赖完整性检查
6. 安全检查（检测硬编码密钥）

**使用示例：**

```python
from silvaengine_base import ConfigValidator, get_config_validator

validator = get_config_validator()

# 验证单个插件配置
result = validator.validate_plugin_config("my_plugin", {
    "type": "my_plugin",
    "module_name": "my_module.plugin",
    "function_name": "init",
    "config": {"key": "value"},
})

if not result.is_valid:
    for error in result.errors:
        print(f"[{error.code}] {error.field}: {error.message}")

for warning in result.warnings:
    print(f"[{warning.code}] {warning.field}: {warning.message}")

# 验证整个插件配置列表
result = validator.validate_plugins_config(plugins_config)
```

---

## 快速开始

### 1. 创建插件模块

创建一个 Python 模块并实现 `init(config)` 函数：

```python
# my_plugin.py
import logging

logger = logging.getLogger(__name__)


def init(config: dict) -> object:
    """
    初始化插件。

    Args:
        config: 插件配置字典，包含用户定义的配置参数

    Returns:
        插件管理器实例

    Raises:
        Exception: 初始化失败时抛出异常
    """
    logger.info(f"Initializing my_plugin with config: {config}")
    return MyPluginManager(config)


class MyPluginManager:
    """插件管理器类。"""

    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "default")

    def get_status(self) -> dict:
        """获取插件状态。"""
        return {"status": "ok", "name": self.name}

    def shutdown(self):
        """关闭插件，释放资源。"""
        logger.info(f"Shutting down my_plugin: {self.name}")
```

### 2. 配置插件

在配置文件中添加插件配置：

```json
{
  "plugins": [
    {
      "type": "my_plugin",
      "module_name": "my_package.my_plugin",
      "function_name": "init",
      "config": {
        "name": "my_instance",
        "setting1": "value1"
      },
      "enabled": true,
      "dependencies": ["other_plugin"]
    }
  ]
}
```

### 3. 在 Lambda 中使用

```python
import logging
from silvaengine_base import Resources

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建 Resources 实例
resources = Resources(logger=logger)

# Lambda handler
def lambda_handler(event, context):
    return resources.handle(event, context)
```

### 4. 在业务代码中使用插件

```python
from silvaengine_base import get_current_plugin_context

def business_function():
    # 获取当前插件上下文
    context = get_current_plugin_context()
    
    if context:
        plugin = context.get("my_plugin")
        if plugin:
            status = plugin.get_status()
            return status
    
    return {"status": "plugin_not_available"}
```

---

## 插件配置格式

### 标准格式（推荐）

```json
{
  "plugins": [
    {
      "type": "plugin_type",
      "module_name": "module.path",
      "function_name": "init",
      "class_name": "OptionalClass",
      "config": {
        "key": "value"
      },
      "enabled": true,
      "dependencies": ["dep_plugin1", "dep_plugin2"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| type | string | 是 | - | 插件类型标识符，必须唯一，小写字母开头 |
| module_name | string | 是 | - | Python 模块路径，如 `my_package.plugin` |
| function_name | string | 否 | "init" | 初始化函数名 |
| class_name | string | 否 | null | 类名（用于实例化后调用方法） |
| config | dict | 否 | {} | 插件配置参数 |
| enabled | bool | 否 | true | 是否启用该插件 |
| dependencies | list | 否 | [] | 依赖的其他插件类型列表 |

### 命名规范

- **插件类型 (type)**: 小写字母开头，只能包含小写字母、数字和下划线
  - ✅ 有效: `connection_pool`, `cache_manager`, `my_plugin_v2`
  - ❌ 无效: `ConnectionPool`, `123_plugin`, `my-plugin`

- **模块名 (module_name)**: 有效的 Python 模块路径
  - ✅ 有效: `my_package.plugin`, `silvaengine_connections`
  - ❌ 无效: `my package.plugin`, `..invalid`, `invalid.`

- **函数名 (function_name)**: 有效的 Python 标识符
  - ✅ 有效: `init`, `initialize`, `create_manager`
  - ❌ 无效: `123_init`, `init-function`

- **类名 (class_name)**: 有效的 Python 类名，建议大驼峰命名
  - ✅ 有效: `PluginManager`, `CacheClient`
  - ❌ 无效: `pluginManager`, `123Class`

### 两种初始化方式

**方式一：直接函数调用（推荐）**

```python
# plugin_module.py
def init(config: dict) -> object:
    return PluginInstance(config)
```

配置：

```json
{
  "module_name": "plugin_module",
  "function_name": "init"
}
```

**方式二：实例化类后调用方法**

```python
# plugin_module.py
class PluginClass:
    def init(self, config: dict) -> object:
        self.config = config
        return self
```

配置：

```json
{
  "module_name": "plugin_module",
  "class_name": "PluginClass",
  "function_name": "init"
}
```

---

## 核心 API 参考

### PluginManager

插件管理器是 silvaengine_base 的核心类，负责插件的注册、初始化和生命周期管理。

```python
from silvaengine_base import PluginManager

# 获取单例实例
manager = PluginManager()
```

#### 主要方法

| 方法 | 签名 | 描述 |
|------|------|------|
| initialize | `initialize(handler_setting: dict) -> bool` | 初始化所有配置的插件 |
| get_initialized_object | `get_initialized_object(plugin_type: str) -> Any` | 获取指定类型的插件实例 |
| get_initialized_objects | `get_initialized_objects() -> dict` | 获取所有插件实例 |
| get_context | `get_context(timeout: float = 30.0) -> PluginContext` | 获取插件上下文 |
| set_parallel_enabled | `set_parallel_enabled(enabled: bool)` | 设置是否启用并行初始化 |
| set_max_workers | `set_max_workers(max_workers: int)` | 设置并行初始化最大工作线程数 |
| is_initialized | `is_initialized() -> bool` | 检查管理器是否已初始化 |
| reset_instance | `reset_instance() -> None` | 重置单例实例（测试用） |

#### 配置方法

| 方法 | 签名 | 描述 |
|------|------|------|
| set_plugin_init_timeout | `set_plugin_init_timeout(timeout: float)` | 设置单个插件初始化超时 |
| set_global_init_timeout | `set_global_init_timeout(timeout: float)` | 设置全局初始化超时 |
| set_circuit_breaker_enabled | `set_circuit_breaker_enabled(enabled: bool)` | 启用/禁用熔断器 |
| set_lazy_loading_enabled | `set_lazy_loading_enabled(enabled: bool)` | 启用/禁用延迟加载 |
| set_validation_strict_mode | `set_validation_strict_mode(strict: bool)` | 设置验证严格模式 |

#### 状态查询方法

| 方法 | 签名 | 描述 |
|------|------|------|
| validate_configuration | `validate_configuration(plugins_config: list) -> ValidationResult` | 验证配置（不初始化） |
| get_plugin_status | `get_plugin_status(plugin_type: str) -> dict` | 获取插件状态 |
| get_all_plugin_status | `get_all_plugin_status() -> dict` | 获取所有插件状态 |

### PluginContext

插件上下文提供线程安全的插件访问机制。

```python
from silvaengine_base import PluginContext

context = PluginContext(plugin_manager)

# 设置插件
context.set_plugin("my_plugin", plugin_instance)

# 获取插件
plugin = context.get("my_plugin")

# 获取所有插件
all_plugins = context.get_all_plugins()

# 检查插件是否存在
exists = context.has_plugin("my_plugin")

# 等待插件初始化
context.wait_for_plugin("my_plugin", timeout=30.0)
```

### PluginContextInjector

```python
from silvaengine_base import (
    PluginContextInjector,
    get_current_plugin_context,
    set_current_plugin_context,
    clear_current_plugin_context,
    inject_plugin_context,
)

# 使用上下文管理器
with PluginContextInjector(plugin_context):
    context = get_current_plugin_context()
    plugin = context.get("my_plugin")

# 设置当前上下文
set_current_plugin_context(plugin_context)

# 获取当前上下文
context = get_current_plugin_context()

# 清除当前上下文
clear_current_plugin_context()
```

### CircuitBreaker

```python
from silvaengine_base import CircuitBreaker, CircuitState, get_circuit_breaker_registry

# 获取熔断器注册表
registry = get_circuit_breaker_registry()

# 创建或获取熔断器
breaker = registry.get_or_create(
    name="my_plugin",
    failure_threshold=3,
    recovery_timeout=60.0,
)

# 使用熔断器
try:
    result = breaker.call(my_function, arg1, arg2)
except Exception as e:
    logger.error(f"Call failed: {e}")

# 获取状态
state = breaker.get_state()
stats = breaker.get_stats()

# 重置
breaker.reset()
```

---

## 配置验证

### 使用 ConfigValidator

silvaengine_base 提供强大的配置验证功能，可在初始化前检测配置错误。

```python
from silvaengine_base import ConfigValidator, get_config_validator

# 获取验证器实例
validator = get_config_validator()

# 或创建新实例
validator = ConfigValidator()

# 验证单个插件配置
result = validator.validate_plugin_config("my_plugin", {
    "type": "my_plugin",
    "module_name": "my_module",
    "function_name": "init",
    "config": {"key": "value"}
})

if not result.is_valid:
    for error in result.errors:
        print(f"Error [{error.code}]: {error.field} - {error.message}")

for warning in result.warnings:
    print(f"Warning [{warning.code}]: {warning.field} - {warning.message}")
```

### 验证规则

验证器会自动检查以下内容：

1. **必需字段**: `type`, `module_name`
2. **类型检查**: `enabled` 必须是布尔值，`dependencies` 必须是列表
3. **格式验证**: 
   - 插件类型必须以小写字母开头
   - 模块名不能包含空格或连续的点
   - 函数名必须是有效的 Python 标识符
   - 类名建议大驼峰命名
4. **保留关键字**: 不能使用 `config`, `enabled`, `module_name` 等保留字作为插件类型
5. **依赖检查**: 确保依赖的插件在配置中已定义
6. **安全检查**: 检测硬编码的密码、密钥等敏感信息

### 验证错误代码

| 代码 | 描述 | 级别 |
|------|------|------|
| MISSING_TYPE | 缺少插件类型 | 错误 |
| INVALID_TYPE | 字段类型不正确 | 错误 |
| INVALID_FORMAT | 格式无效 | 错误 |
| MISSING_FIELD | 缺少必需字段 | 错误 |
| RESERVED_NAME | 使用了保留关键字 | 错误 |
| DUPLICATE_PLUGIN | 重复的插件类型 | 错误 |
| MISSING_DEPENDENCY | 依赖的插件未定义 | 错误 |
| HARDCODED_SECRET | 检测到硬编码密钥 | 警告 |
| NAMING_CONVENTION | 命名规范建议 | 警告 |

---

## 插件生命周期管理

### 插件状态

```
REGISTERED -> INITIALIZING -> ACTIVE
                              |
                              v
                           FAILED -> (可重试) -> INITIALIZING
                              |
                              v
                           DISABLED
                              |
                              v
                        UNREGISTERED
```

| 状态 | 描述 |
|------|------|
| REGISTERED | 已注册，等待初始化 |
| INITIALIZING | 正在初始化 |
| ACTIVE | 初始化成功，运行中 |
| FAILED | 初始化失败 |
| DISABLED | 已禁用 |
| UNREGISTERED | 已注销 |

### 生命周期钩子

插件可以实现以下生命周期钩子：

```python
class MyPlugin:
    def __init__(self, config: dict):
        """初始化插件。"""
        self.config = config
        self._setup()
    
    def _setup(self):
        """设置资源。"""
        pass
    
    def shutdown(self):
        """关闭插件，释放资源。"""
        pass
    
    def health_check(self) -> dict:
        """健康检查。"""
        return {"status": "healthy"}
```

---

## 高级特性

### 1. 并行初始化

PluginManager 支持并行初始化多个插件，显著减少初始化时间。

```python
from silvaengine_base import PluginManager

manager = PluginManager()
manager.set_parallel_enabled(True)
manager.set_max_workers(8)  # 设置最大并发数

# 初始化时会并行处理无依赖关系的插件
manager.initialize(setting)
```

**注意事项：**

- 有依赖关系的插件会按拓扑顺序初始化
- 无依赖关系的插件会并行初始化
- 每个插件有独立的超时控制

### 2. 熔断器模式

防止故障插件反复失败影响系统稳定性。

```python
manager = PluginManager()
manager.set_circuit_breaker_enabled(True)

# 熔断器配置
# - failure_threshold: 失败次数阈值，默认 3
# - recovery_timeout: 恢复超时时间，默认 60 秒
```

**熔断器状态转换：**

1. **CLOSED → OPEN**: 连续失败次数超过阈值
2. **OPEN → HALF_OPEN**: 超过恢复超时时间
3. **HALF_OPEN → CLOSED**: 测试调用成功
4. **HALF_OPEN → OPEN**: 测试调用失败

### 3. 延迟加载

按需初始化插件，优化 Lambda 冷启动性能。

```python
manager = PluginManager()
manager.set_lazy_loading_enabled(True)

# 初始化时不会立即加载插件
manager.initialize(setting)

# 第一次访问时才初始化
plugin = manager.get_initialized_object("my_plugin")
```

**适用场景：**

- Lambda 冷启动优化
- 资源密集型插件
- 可能不会用到的插件

### 4. 依赖管理

自动解析插件依赖关系，确保正确的初始化顺序。

```json
{
  "plugins": [
    {
      "type": "database",
      "module_name": "plugins.database",
      "function_name": "init"
    },
    {
      "type": "cache",
      "module_name": "plugins.cache",
      "function_name": "init",
      "dependencies": ["database"]
    },
    {
      "type": "api",
      "module_name": "plugins.api",
      "function_name": "init",
      "dependencies": ["database", "cache"]
    }
  ]
}
```

**初始化顺序：** database → cache → api

### 5. 上下文注入

通过线程本地存储实现插件上下文的自动传递。

```python
from silvaengine_base import Handler, get_current_plugin_context

class MyHandler(Handler):
    def handle(self):
        # 方式一：使用描述符
        plugin = self.plugin_context.get("my_plugin")
        
        # 方式二：使用全局函数
        context = get_current_plugin_context()
        plugin = context.get("my_plugin")
        
        return {"result": plugin.do_something()}
```

---

## 事件处理器开发

### Handler 基类

所有事件处理器都继承自 `Handler` 基类。

```python
from silvaengine_base.handler import Handler

class MyCustomHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: dict) -> bool:
        """判断事件是否匹配此处理器。"""
        return "my_custom_key" in event
    
    def handle(self) -> Any:
        """处理事件。"""
        # 使用基类提供的辅助方法
        endpoint_id = self._get_endpoint_id()
        api_key = self._get_api_key()
        
        # 获取插件上下文
        plugin = self.plugin_context.get("my_plugin")
        
        # 调用业务逻辑
        return self._get_proxied_callable(
            module_name="my_module",
            class_name="MyClass",
            function_name="my_function",
        )(param1="value1", param2="value2")
```

### Handler 辅助方法

| 方法 | 描述 |
|------|------|
| `_get_endpoint_id()` | 获取端点 ID |
| `_get_api_key()` | 获取 API 密钥 |
| `_get_api_stage()` | 获取 API 阶段 |
| `_get_api_area()` | 获取 API 区域 |
| `_get_request_method()` | 获取 HTTP 方法 |
| `_get_headers()` | 获取请求头 |
| `_get_query_string_parameters()` | 获取查询参数 |
| `_get_path_parameters()` | 获取路径参数 |
| `_parse_event_body()` | 解析请求体 |
| `_get_authorized_user()` | 获取授权用户信息 |
| `_get_function_and_setting()` | 获取函数配置 |
| `_invoke_authorization(action)` | 调用授权 |
| `_get_proxied_callable()` | 获取可调用代理 |
| `_get_metadata()` | 获取元数据 |

### 内置事件处理器

#### HttpHandler

处理 HTTP API 请求（API Gateway）。

**事件匹配规则：**

```python
# HTTP API (v2)
"requestContext" in event and "http" in event["requestContext"]

# REST API (v1)
"requestContext" in event and "resourcePath" in event["requestContext"]
```

**处理流程：**

1. 提取核心参数（endpoint_id, api_key, function_name）
2. 获取函数配置
3. 验证授权（如果需要）
4. 调用业务函数

#### WebSocketHandler

处理 WebSocket 连接和消息。

**事件匹配规则：**

```python
"requestContext" in event and "connectionId" in event["requestContext"]
```

**路由处理：**

- `$connect`: 建立连接
- `$disconnect`: 断开连接
- `stream`: 消息流

#### LambdaInvocationHandler

处理 Lambda 之间的调用。

**事件格式：**

```json
{
  "__type": "lambda_invocation",
  "__execution_start_time": 1234567890.123,
  "context": {
    "endpoint_id": "my_endpoint",
    "aws_api_stage": "prod",
    "aws_api_area": "core"
  },
  "module_name": "my_module",
  "class_name": "MyClass",
  "function_name": "my_function",
  "parameters": {}
}
```

#### DynamodbHandler

处理 DynamoDB 流事件。

**事件匹配规则：**

```python
"Records" in event and event["Records"][0].get("eventSource") == "aws:dynamodb"
```

#### S3Handler

处理 S3 事件。

**事件匹配规则：**

```python
"Records" in event and "s3" in event["Records"][0]
```

**路径解析：**

S3 对象键格式：`{endpoint_id}/{function_name}/...`

#### SQSHandler

处理 SQS 消息。

**事件匹配规则：**

```python
"Records" in event and event["Records"][0].get("eventSource") == "aws:sqs"
```

**消息属性：**

- `endpoint_id`: 端点 ID
- `funct`: 函数名

#### CognitoHandler

处理 Cognito 触发器。

**事件匹配规则：**

```python
all(key in event for key in ["triggerSource", "userPoolId", "request", "response"])
```

---

## 最佳实践

### 1. 插件设计原则

- **单一职责**: 每个插件只负责一个功能领域
- **配置驱动**: 通过配置控制插件行为，避免硬编码
- **优雅降级**: 插件初始化失败不应影响其他插件
- **资源管理**: 实现 `shutdown()` 方法释放资源

### 2. 错误处理

```python
def init(config: dict) -> object:
    try:
        # 验证必需配置
        required_keys = ["host", "port"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config: {key}")

        return PluginManager(config)
    except Exception as e:
        logger.error(f"Failed to initialize plugin: {e}")
        raise  # 重新抛出，让上层处理
```

### 3. 日志记录

```python
import logging

logger = logging.getLogger(__name__)

def init(config: dict) -> object:
    logger.info(f"Initializing plugin with config: {config}")

    try:
        manager = PluginManager(config)
        logger.info("Plugin initialized successfully")
        return manager
    except Exception as e:
        logger.error(f"Plugin initialization failed: {e}")
        raise
```

### 4. 配置验证

```python
def init(config: dict) -> object:
    # 验证配置类型
    if not isinstance(config, dict):
        raise TypeError("Config must be a dictionary")

    # 设置默认值
    host = config.get("host", "localhost")
    port = config.get("port", 8080)

    # 验证数值范围
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid port: {port}")

    return PluginManager(host=host, port=port)
```

### 5. 依赖管理

```python
# 在插件中检查依赖
def init(config: dict) -> object:
    from silvaengine_base import PluginManager

    manager = PluginManager()

    # 检查依赖插件是否已初始化
    base_plugin = manager.get_initialized_object("base_plugin")
    if base_plugin is None:
        raise RuntimeError("Required plugin 'base_plugin' not initialized")

    return MyPlugin(base_plugin)
```

### 6. 线程安全

```python
import threading

class PluginManager:
    def __init__(self, config: dict):
        self._config = config
        self._lock = threading.RLock()
        self._data = {}

    def get_data(self, key: str):
        with self._lock:
            return self._data.get(key)

    def set_data(self, key: str, value):
        with self._lock:
            self._data[key] = value
```

### 7. Lambda 冷启动优化

```python
from silvaengine_base import Resources

# 启用延迟加载
resources = Resources(
    logger=logger,
    lazy_loading_enabled=True,      # 延迟加载
    parallel_enabled=True,          # 并行初始化
    plugin_init_timeout=10.0,       # 减少超时时间
    global_init_timeout=30.0,       # 减少全局超时
)
```

---

## 完整示例

### 示例 1：缓存插件（Redis）

```python
# cache_plugin.py
import logging
import redis
from typing import Optional

logger = logging.getLogger(__name__)


def init(config: dict) -> "CacheManager":
    """初始化缓存插件。"""
    return CacheManager(config)


class CacheManager:
    """Redis 缓存管理器。"""

    def __init__(self, config: dict):
        self._config = config
        self._client = None
        self._connect()

    def _connect(self):
        """建立 Redis 连接。"""
        try:
            self._client = redis.Redis(
                host=self._config.get("host", "localhost"),
                port=self._config.get("port", 6379),
                db=self._config.get("db", 0),
                password=self._config.get("password"),
                decode_responses=True
            )
            # 测试连接
            self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def get(self, key: str) -> Optional[str]:
        """获取缓存值。"""
        try:
            return self._client.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    def set(self, key: str, value: str, expire: int = None) -> bool:
        """设置缓存值。"""
        try:
            return self._client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存。"""
        try:
            return bool(self._client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def shutdown(self):
        """关闭连接。"""
        if self._client:
            self._client.close()
            logger.info("Redis connection closed")
```

配置：

```json
{
  "plugins": [
    {
      "type": "cache",
      "module_name": "my_plugins.cache_plugin",
      "function_name": "init",
      "config": {
        "host": "${REDIS_HOST}",
        "port": 6379,
        "db": 0,
        "password": "${REDIS_PASSWORD}"
      },
      "enabled": true
    }
  ]
}
```

### 示例 2：数据库连接池插件

```python
# db_plugin.py
import logging
import psycopg2.pool
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def init(config: dict) -> "DatabaseManager":
    """初始化数据库插件。"""
    return DatabaseManager(config)


class DatabaseManager:
    """PostgreSQL 数据库管理器。"""

    def __init__(self, config: dict):
        self._config = config
        self._pool = None
        self._init_pool()

    def _init_pool(self):
        """初始化连接池。"""
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self._config.get("min_connections", 1),
                maxconn=self._config.get("max_connections", 10),
                host=self._config["host"],
                port=self._config.get("port", 5432),
                database=self._config["database"],
                user=self._config["username"],
                password=self._config["password"]
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to init database pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）。"""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)

    def execute(self, query: str, params: tuple = None):
        """执行 SQL 查询。"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
                return cursor.fetchall()

    def shutdown(self):
        """关闭连接池。"""
        if self._pool:
            self._pool.closeall()
            logger.info("Database connection pool closed")
```

配置：

```json
{
  "plugins": [
    {
      "type": "database",
      "module_name": "my_plugins.db_plugin",
      "function_name": "init",
      "config": {
        "host": "${DB_HOST}",
        "port": 5432,
        "database": "myapp",
        "username": "${DB_USER}",
        "password": "${DB_PASSWORD}",
        "min_connections": 2,
        "max_connections": 10
      },
      "enabled": true
    }
  ]
}
```

### 示例 3：自定义事件处理器

```python
# my_handler.py
import logging
from typing import Any, Dict
from silvaengine_base.handler import Handler

logger = logging.getLogger(__name__)


class MyCustomHandler(Handler):
    """自定义事件处理器。"""
    
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        """判断是否匹配此处理器。"""
        return "my_custom_event_type" in event
    
    def handle(self) -> Any:
        """处理事件。"""
        try:
            # 提取事件数据
            event_data = self.event.get("my_custom_event_type", {})
            
            # 获取插件
            cache = self.plugin_context.get("cache")
            database = self.plugin_context.get("database")
            
            # 业务逻辑
            result = self._process_event(event_data, cache, database)
            
            return {
                "statusCode": 200,
                "body": result
            }
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            raise
    
    def _process_event(self, data, cache, database):
        """处理事件逻辑。"""
        # 实现业务逻辑
        return {"status": "processed", "data": data}
```

注册处理器：

```python
# 在 Resources 中注册
from silvaengine_base import Resources
from my_handler import MyCustomHandler

class MyResources(Resources):
    _event_handlers = [
        MyCustomHandler,  # 添加自定义处理器
        *Resources._event_handlers,  # 保留原有处理器
    ]
```

### 示例 4：多插件配置

```json
{
  "plugins": [
    {
      "type": "database",
      "module_name": "my_plugins.db_plugin",
      "function_name": "init",
      "config": {
        "host": "${DB_HOST}",
        "port": 5432,
        "database": "mydb",
        "username": "${DB_USER}",
        "password": "${DB_PASSWORD}",
        "min_connections": 2,
        "max_connections": 10
      },
      "enabled": true
    },
    {
      "type": "cache",
      "module_name": "my_plugins.cache_plugin",
      "function_name": "init",
      "config": {
        "host": "${REDIS_HOST}",
        "port": 6379
      },
      "enabled": true,
      "dependencies": ["database"]
    },
    {
      "type": "queue",
      "module_name": "my_plugins.queue_plugin",
      "function_name": "init",
      "config": {
        "backend": "rabbitmq",
        "host": "${RABBITMQ_HOST}"
      },
      "enabled": true,
      "dependencies": ["cache"]
    }
  ]
}
```

---

## 故障排除

### 常见问题

#### 1. 插件初始化失败

**现象**: `PluginManager.initialize()` 返回 `False`

**排查步骤**:

1. 检查配置格式是否正确
2. 验证 `module_name` 指向的模块是否存在
3. 检查 `function_name` 指定的函数是否可调用
4. 查看日志中的错误信息

```python
from silvaengine_base import ConfigValidator

validator = ConfigValidator()
result = validator.validate_plugins_config(plugins_config)

if not result.is_valid:
    for error in result.errors:
        print(f"[{error.code}] {error.field}: {error.message}")
```

#### 2. 插件未找到

**现象**: `get_initialized_object()` 返回 `None`

**原因**:

- 插件类型名称拼写错误（区分大小写）
- 插件初始化失败
- 插件被禁用 (`enabled: false`)

**解决**:

```python
# 检查插件状态
status = manager.get_plugin_status("my_plugin")
print(status)

# 检查所有插件
all_status = manager.get_all_plugin_status()
for plugin_type, info in all_status.items():
    print(f"{plugin_type}: {info}")
```

#### 3. 依赖问题

**现象**: 插件初始化顺序错误，依赖插件未就绪

**解决**:

- 确保在配置中正确声明 `dependencies`
- 检查是否存在循环依赖

```python
from silvaengine_base.boosters.plugin.dependency import DependencyResolver, PluginDependency

resolver = DependencyResolver()
plugins = [
    PluginDependency(plugin_name="a", dependencies=["b"]),
    PluginDependency(plugin_name="b", dependencies=["a"]),
]
circular = resolver.detect_circular_dependencies(plugins)
if circular:
    print(f"Circular dependency: {circular}")
```

#### 4. 配置验证警告

**现象**: 出现 `HARDCODED_SECRET` 警告

**解决**:

- 使用环境变量替代硬编码的密码/密钥
- 使用配置占位符如 `"${ENV_VAR}"`

```json
{
  "config": {
    "password": "${DB_PASSWORD}",
    "api_key": "${API_KEY}"
  }
}
```

#### 5. 熔断器阻止初始化

**现象**: 插件初始化被熔断器阻止

**解决**:

```python
from silvaengine_base import get_circuit_breaker_registry

registry = get_circuit_breaker_registry()
breaker = registry.get("my_plugin")

if breaker:
    stats = breaker.get_stats()
    print(f"State: {stats['state']}")
    print(f"Failures: {stats['failure_count']}")
    
    # 重置熔断器
    breaker.reset()
```

### 调试技巧

1. **启用详细日志**:
   
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **验证配置不初始化**:
   
   ```python
   result = manager.validate_configuration(plugins_config)
   print(f"Valid: {result.is_valid}")
   for error in result.errors:
       print(f"Error: {error.message}")
   ```

3. **检查插件注册状态**:
   
   ```python
   status = manager.get_all_plugin_status()
   print(status)
   ```

4. **检查熔断器状态**:
   
   ```python
   from silvaengine_base import get_circuit_breaker_registry
   
   registry = get_circuit_breaker_registry()
   all_stats = registry.get_all_stats()
   for name, stats in all_stats.items():
       print(f"{name}: {stats['state']}")
   ```

---

## 向后兼容性

### 支持的遗留格式

为确保现有配置继续工作，系统支持以下遗留格式：

**1. 使用 `resources` 替代 `config`**:
```json
{
  "plugins": [
    {
      "type": "my_plugin",
      "resources": {"key": "value"}
    }
  ]
}
```

**2. 嵌套格式**:

```json
{
  "plugins": [
    {
      "connection_pools": {
        "postgresql": {...}
      }
    }
  ]
}
```

### 迁移建议

新插件建议使用标准格式（`type` + `config`），旧格式将在未来版本中弃用。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-02-25 | 初始版本，包含完整的插件开发指南 |
| 1.1.0 | 2026-02-25 | 新增配置验证、插件注册管理、异步初始化章节 |
| 2.0.0 | 2026-03-03 | 全面更新：架构概览、核心组件详解、事件处理器开发、最佳实践 |

---

## 参考资源

- [SilvaEngine Base README](README.md)
- [配置 Schema](config.schema.json)
- [API 文档](https://github.com/silvaengine/base)

---

**文档维护**: SilvaEngine Team  
**最后更新**: 2026-03-03
