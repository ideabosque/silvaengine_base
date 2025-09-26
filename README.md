# SilvaEngine Base

A powerful AWS Lambda-based framework for building serverless applications with advanced routing, caching, and WebSocket support.

## 🚀 Features

- **Dual Protocol Support**: HTTP/REST API and WebSocket handling in a unified framework
- **Advanced Caching System**: High-performance hybrid Redis/disk caching with management APIs
- **Dynamic Function Routing**: Endpoint-based routing with runtime function discovery
- **WebSocket Management**: Real-time bidirectional communication with connection lifecycle management
- **AWS Event Processing**: Support for SQS, S3, DynamoDB streams, and Cognito triggers
- **Performance Optimized**: Lazy loading, conditional event data, and comprehensive caching

## 📦 Installation

```bash
pip install silvaengine-base
```

## 🏗️ Architecture

### Core Components

- **`Resources`** - Main API gateway and WebSocket handler
- **`LambdaBase`** - Base class for Lambda operations with AWS integration
- **`Tasks`** - Event-driven task processor for various AWS event sources
- **`Worker`** - Dynamic function executor with runtime module loading
- **Data Models** - DynamoDB models for endpoints, connections, and functions

### Request Flow

```
HTTP/WebSocket Request → Resources → Function Lookup → Authorization → Execution
                                 ↓
                         Cache Management (if proxy operation)
```

## 🎯 Quick Start

### Basic Lambda Handler

```python
from silvaengine_base import Resources

def lambda_handler(event, context):
    """Main Lambda entry point."""
    resources = Resources()
    return resources.handler(event, context)
```

### Function Implementation

```python
from silvaengine_utility import method_cache

class MyService:
    @method_cache(ttl=1800, cache_name="settings")
    def get_settings(self, key: str) -> dict:
        """Get settings with 30-minute cache."""
        return expensive_settings_lookup(key)

    @method_cache(ttl=600, cache_name="database")
    def get_user_data(self, user_id: str) -> dict:
        """Get user data with 10-minute cache."""
        return database.query(user_id)
```

## 🔧 Configuration

### Environment Variables

```bash
REGIONNAME=us-east-1                    # AWS region
FULL_EVENT_AREAS=admin,debug            # Areas requiring complete event data
DYNAMODBSTREAMENDPOINTID=stream-123     # DynamoDB stream endpoint
SNSTOPICARN=arn:aws:sns:...             # SNS topic for error notifications
```

### DynamoDB Tables

The framework requires the following DynamoDB tables:

- `se-endpoints` - Endpoint configurations
- `se-connections` - API connections and function mappings
- `se-functions` - Lambda function definitions
- `se-hooks` - Event hooks configuration
- `se-wss-connections` - WebSocket connection states
- `se-configdata` - Application settings and configuration

## 🌐 API Routing

### HTTP/REST API

```
GET /area/endpoint_id/function_name/path?param=value
POST /area/endpoint_id/function_name
```

### WebSocket API

```javascript
// Connect
const ws = new WebSocket('wss://api.example.com?endpointId=my-app&area=production');

// Send message
ws.send(JSON.stringify({
    funct: 'processData',
    payload: JSON.stringify({ key: 'value' })
}));
```

## 🚄 Advanced Caching System

### Cache Decorators

```python
from silvaengine_utility import method_cache, hybrid_cache

class DataService:
    @method_cache(ttl=1800, cache_name="settings")
    def get_config(self, key: str) -> dict:
        """Cache configuration data for 30 minutes."""
        return fetch_config(key)

    @method_cache(ttl=600, cache_name="database")
    def query_user(self, user_id: str) -> dict:
        """Cache database queries for 10 minutes."""
        return db.get_user(user_id)

    @hybrid_cache(ttl=300, cache_name="api")
    def external_api_call(self, endpoint: str) -> dict:
        """Cache external API calls for 5 minutes."""
        return requests.get(endpoint).json()
```

### Cache Management API

The framework provides RESTful endpoints for cache management:

#### Clear Cache

```bash
# Clear all cache entries for "method" cache
GET /area/endpoint_id/cache_clear

# Clear specific cache instance
GET /area/endpoint_id/cache_clear?cache_name=settings

# Clear specific pattern
GET /area/endpoint_id/cache_clear?cache_name=database&cache_key=user:*
```

#### Cache Statistics

```bash
# Get cache stats for default "method" cache
GET /area/endpoint_id/cache_stats

# Get stats for specific cache instance
GET /area/endpoint_id/cache_stats?cache_name=database
```

#### Response Format

```json
{
  "success": true,
  "cache_name": "database",
  "redis_available": true,
  "disk_available": true,
  "disk_path": "/tmp/silvaengine_cache/database"
}
```

### Cache Performance

| Operation Type | Without Cache | With Cache | Improvement |
|---------------|---------------|------------|-------------|
| Settings Lookup | 200ms | 1-3ms | **98%** |
| Database Query | 150ms | 1-3ms | **98%** |
| API Calls | 300ms | 1-3ms | **99%** |

## 🔌 WebSocket Support

### Connection Management

```python
# Automatic connection handling
def on_connect(event, context):
    # Connection automatically stored in DynamoDB
    # with 24-hour TTL and area-based routing
    pass

def on_message(event, context):
    # Real-time message processing
    # with authentication and routing
    pass
```

### WebSocket Events

- **`$connect`** - Connection establishment
- **`$disconnect`** - Connection cleanup
- **`stream`** - Message processing with function routing

## 🔐 Security & Authorization

### API Key Authentication

```python
# Automatic API key validation
# Headers: x-api-key or query parameter
```

### Dynamic Authorization

```python
def custom_authorizer(event, context, action):
    """Custom authorization logic."""
    if action == "authorize":
        # Handle initial authorization
        return authorization_result
    elif action == "verify_permission":
        # Handle permission verification
        return permission_result
```

## 📊 Event Source Processing

### Supported Event Sources

- **SQS Events** - Message queue processing
- **S3 Events** - File upload/change triggers
- **DynamoDB Streams** - Real-time data change processing
- **Cognito Triggers** - User authentication hooks
- **AWS Lex** - Chatbot integration

### Event Processing

```python
def process_sqs_event(records):
    """Process SQS messages."""
    for record in records:
        # Handle message
        pass

def process_s3_event(records):
    """Process S3 object events."""
    for record in records:
        # Handle file changes
        pass
```

## 🛠️ Performance Optimizations

### Recent Performance Updates

1. **Event Data Normalization** - Converts ConfigMap objects to dictionaries
2. **Lazy Context Creation** - AWS context objects only created when needed
3. **Conditional Full Event Data** - Only includes complete event data for specific areas
4. **Authorization Streamlining** - Simplified permission verification flow

### Caching Strategy

- **Settings**: 30-minute TTL for configuration data
- **Database**: 10-minute TTL for connection lookups
- **API Calls**: 5-minute TTL for external services
- **Pattern-based Invalidation** - Selective cache clearing

## 🐛 Error Handling

### Custom Error Types

```python
from silvaengine_base import FunctionError

# Lambda-specific error handling
raise FunctionError("Custom error message", status_code=400)
```

### Monitoring

- **Structured Logging** - Comprehensive logging throughout
- **SNS Notifications** - Error reporting via SNS
- **Runtime Debugging** - Execution time tracking
- **Request ID Tracking** - Duplicate request prevention

## 📈 Development

### Dependencies

- **Core**: `silvaengine_utility`, `boto3`, `pynamodb`
- **Optional**: `redis` (for Redis caching), `pyyaml`

### Testing

```bash
# Run tests
python -m pytest tests/

# Test cache performance
python -m pytest tests/test_cache_performance.py -v
```

## 🔄 Migration Guide

### From Legacy Cache System

```python
# Old approach (removed)
@settings_cache(ttl=1800)
@database_cache(ttl=600)

# New unified approach
@method_cache(ttl=1800, cache_name="settings")
@method_cache(ttl=600, cache_name="database")
```

## 📝 API Reference

### Core Classes

#### Resources

Main handler class for HTTP and WebSocket requests.

```python
class Resources:
    def handler(self, event, context) -> dict:
        """Main Lambda entry point."""
        pass

    def _handle_cache_management(self, operation: str, params: dict) -> dict:
        """Handle cache management operations."""
        pass
```

#### LambdaBase

Base class for Lambda operations.

```python
class LambdaBase:
    @staticmethod
    def invoke(arn: str, payload: dict, invocation_type: str = "RequestResponse"):
        """Invoke Lambda function."""
        pass

    @staticmethod
    def get_function(endpoint_id: str, funct: str, api_key: str, method: str):
        """Get function configuration."""
        pass
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add comprehensive tests
4. Update documentation
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Support

For support and questions:
- GitHub Issues: [Report Issues](https://github.com/ideabosque/silvaengine_base/issues)
- Documentation: [Full API Docs](https://docs.silvaengine.com)

---

**SilvaEngine Base** - Powering serverless applications with advanced caching and real-time capabilities.