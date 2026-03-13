#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
import os
import time
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import boto3
from silvaengine_dynamodb_base.models import (
    ConfigModel,
    ConnectionModel,
    FunctionModel,
    GraphqlSchemaModel,
)

from silvaengine_constants import (
    AuthorizationAction,
    AuthorizationType,
    EventType,
    HttpStatus,
    InvocationType,
    RequestMethod,
)
from silvaengine_utility import (
    Authorizer,
    Debugger,
    HttpResponse,
    Invoker,
    Serializer,
    Utility,
)

from .boosters.plugin import PluginContext, PluginManager
from .boosters.plugin.injector import (
    PluginContextDescriptor,
    PluginContextInjector,
    get_current_plugin_context,
    set_current_plugin_context,
)


class Handler:
    aws_client: Any = None
    plugin_context: PluginContextDescriptor = PluginContextDescriptor()
    # Class-level cache for proxied callables to avoid repeated module resolution
    _callable_cache: Dict[str, Callable] = {}

    def __init__(
        self,
        event: Dict[str, Any],
        context: Any,
        setting: Dict[str, Any],
        logger: logging.Logger,
    ) -> None:
        self.logger = (
            logger
            if isinstance(logger, logging.Logger)
            else logging.getLogger(__name__)
        )
        self.event = event or {}
        self.context = context
        self.setting = setting or {}

    def handle(self) -> Any:
        raise NotImplementedError("Subclasses must implement the handle method.")

    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        raise NotImplementedError("Subclasses must implement the handle method.")

    @classmethod
    def new_handler(
        cls,
        event: Dict[str, Any],
        context: Any,
        setting: Dict[str, Any],
        logger: logging.Logger,
    ) -> "Handler":
        """
        Factory method to create a new handler instance.

        This method creates and returns a handler instance with the provided
        event, context, and logger. Subclasses can override this method to
        customize handler creation behavior.

        Args:
            event: The Lambda event dictionary
            context: The Lambda context object
            logger: The logger instance for logging

        Returns:
            A new Handler instance
        """
        return cls(
            event=event,
            context=context,
            setting=setting,
            logger=logger,
        )._initialize()

    def _generate_response(self, status_code: int, body: Any) -> Dict[str, Any]:
        """Generate a standard HTTP response."""
        return HttpResponse.format_response(status_code=status_code, data=body)

    def _merge_setting_to_default(self, setting: Dict[str, Any]) -> "Handler":
        if isinstance(setting, dict):
            self.setting.update(setting)
        return self

    def _merge_metadata_to_event(self, metadata: Any) -> "Handler":
        if isinstance(metadata, dict):
            self.event.update(metadata)
        return self

    def _invoke_authorization(self, action: AuthorizationAction) -> Any:
        """Dynamically handle authorization and permission checks."""
        module_name = self.setting.get(
            "authorizer_module_name",
            "silvaengine_authorizer",
        )
        class_name = self.setting.get(
            "authorizer_class_name",
            "Authorizer",
        )

        if action == AuthorizationAction.AUTHORIZE:
            function_name = self.setting.get(
                "authorizer_authorize_function_name",
                "authorize",
            )

            return self._get_proxied_callable(
                module_name=module_name,
                function_name=function_name,
                class_name=class_name,
            )(self.event, self.context)
        elif action == AuthorizationAction.VERIFY_PERMISSION:
            function_name = self.setting.get(
                "authorizer_verify_permission_function_name",
                "verify_permission",
            )

            return self._get_proxied_callable(
                module_name=module_name,
                function_name=function_name,
                class_name=class_name,
            )(self.event, self.context)

        raise Exception("Invalid authorization action")

    @classmethod
    def _get_aws_client(cls, client_type: str = "lambda") -> Any:
        if not cls.aws_client:
            region = os.getenv("REGION_NAME", os.getenv("REGIONNAME", "us-east-1"))
            cls.aws_client = boto3.client(
                str(client_type).strip().lower(),
                region_name=region,
            )
        return cls.aws_client

    @classmethod
    def invoke_aws_lambda_function(
        cls,
        function_name: str,
        payload: Dict[str, Any],
        invocation_type: InvocationType = InvocationType.EVENT,
        qualifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke another Lambda function.

        Args:
            function_name: The name of the Lambda function to invoke.
            payload: The payload to pass to the function.
            invocation_type: The invocation type (EVENT, REQUEST_RESPONSE, or DRY_RUN).
            qualifier: The function version or alias (optional).

        Returns:
            The response from the invoked function, or an empty dict if EVENT type.

        Raises:
            ValueError: If function_name is empty or invocation_type is invalid.
            Exception: If the invocation fails or response is invalid.
        """
        if not function_name:
            raise ValueError("Function name is required")
        elif not isinstance(payload, dict):
            payload = {}

        valid_invocation_types = {
            InvocationType.EVENT,
            InvocationType.REQUEST_RESPONSE,
            InvocationType.DRY_RUN,
        }

        if invocation_type not in valid_invocation_types:
            raise ValueError(f"Invalid invocation_type: {invocation_type.value}")

        try:
            payload.update(
                __execution_start_time=time.time(),
                __type=EventType.LAMBDA_INVOCATION.value,
            )

            function_payload = Serializer.json_dumps(payload, separators=(",", ":"))
            response = cls._get_aws_client().invoke(
                FunctionName=function_name,
                InvocationType=invocation_type.value,
                Payload=function_payload,
                Qualifier=qualifier,
            )

            if "Payload" not in response:
                raise Exception("Invalid response structure")
            elif invocation_type == InvocationType.REQUEST_RESPONSE:
                try:
                    payload_content = response["Payload"].read()

                    return (
                        Serializer.json_loads(payload_content)
                        if payload_content
                        else {}
                    )
                except Exception:
                    raise
        except Exception:
            raise

    @classmethod
    def _get_function_and_setting(
        cls,
        endpoint_id: str,
        function_name: str,
        api_key: str = "#####",
        method: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], FunctionModel]:
        """Fetch the function configuration for a given endpoint."""
        try:
            endpoint_id = str(endpoint_id).strip()

            if not endpoint_id:
                raise ValueError("Invalid endpoint id")

            function_name = str(function_name).strip()

            if not function_name:
                raise ValueError("Invalid function name")

            api_key = str(api_key).strip()

            if not api_key:
                raise ValueError("Invalid api key")

            connection = ConnectionModel.get(hash_key=endpoint_id, range_key=api_key)
            middleman = next(
                (
                    fn
                    for fn in connection.functions
                    if hasattr(fn, "function") and fn.function == function_name
                ),
                None,
            )

            if (
                not middleman
                or not hasattr(middleman, "aws_lambda_arn")
                or not hasattr(middleman, "function")
                or not hasattr(middleman, "setting")
            ):
                raise ValueError(
                    f"Cannot find the function({function_name}) with endpoint_id({endpoint_id})."
                )

            function = FunctionModel.get(
                middleman.aws_lambda_arn,
                middleman.function,
            )

            if (
                not function
                or not hasattr(function, "config")
                or not hasattr(function.config, "methods")
                or not hasattr(function.config, "setting")
            ):
                raise ValueError(
                    "Cannot locate the function!! Please check the path and parameters."
                )

            if method and method not in function.config.methods:
                raise ValueError(
                    f"The function({function_name}) doesn't support the method({method})."
                )

            # Merge settings from connection and function, connection settings override function settings
            function_setting = (
                ConfigModel.find(setting_id=function.config.setting)
                if function.config.setting
                else {}
            )
            connection_setting = (
                ConfigModel.find(setting_id=middleman.setting)
                if middleman.setting
                else {}
            )

            if len(function_setting) >= len(connection_setting):
                function_setting.update(connection_setting)
                return function_setting, function

            connection_setting.update(function_setting)
            return connection_setting, function
        except Exception as e:
            raise ValueError(f"Failed to get function {function_name}: {str(e)}")

    def _is_authorization_event(self) -> bool:
        """Check if the event is a request event."""
        return bool(
            str(self.event.get("type")).strip().upper()
            in [
                AuthorizationType.REQUEST.name,
                AuthorizationType.TOKEN.name,
            ]
        )

    def _validate_function_area(self, function_area: str) -> None:
        """Validate if the area matches the function configuration."""
        area = self._get_api_area()

        if area != function_area:
            raise RuntimeError(
                f"Area ({area}) does not match the function ({function_area})."
            )

    def _get_request_method(self) -> str:
        """Get the HTTP method from the event."""
        default_request_method = RequestMethod.POST.name
        context = self.event.get("requestContext")

        if not isinstance(context, dict):
            return default_request_method

        return context.get("http", {}).get("method") or context.get(
            "httpMethod", default_request_method
        )

    def _get_endpoint_id(self) -> str:
        return (
            str(
                self.event.get("pathParameters", {}).get("endpoint_id")
                or str(self.context.function_name).split("_")[0]
            )
            .strip()
            .lower()
        )

    def _get_api_stage(self) -> str:
        return self.event.get("requestContext", {}).get("stage") or "beta"

    def _get_api_area(self) -> str:
        return self.event.get("pathParameters", {}).get("area", "core")

    def _get_api_proxy(self) -> str:
        return self.event.get("pathParameters", {}).get("proxy", "")

    def _get_proxy_function_and_path(self) -> Tuple[str, str]:
        proxy = self._get_api_proxy()

        if not proxy:
            raise ValueError("`proxy` is required in path parameters")

        function_name = str(proxy.split("/")[0] if proxy else "").strip()

        if not function_name:
            raise ValueError("missing `function_name` in request")

        path = ""

        if "/" in proxy:
            path = str(proxy.split("/", 1)[1]).strip()

        return function_name, path

    def _get_header(self, key: str) -> Optional[str]:
        return self.event.get("headers", {}).get(str(key).strip())

    def _get_query_string_parameter(self, key: str) -> Optional[str]:
        return self.event.get("queryStringParameters", {}).get(str(key).strip())

    def _get_request_context(self) -> Dict[str, Any]:
        return self.event.get("requestContext", {}) or {}

    def _get_path_parameters(self) -> Dict[str, Any]:
        return self.event.get("pathParameters", {}) or {}

    def _get_headers(self) -> Dict[str, Any]:
        return self.event.get("headers", {}) or {}

    def _get_query_string_parameters(self) -> Dict[str, Any]:
        return self.event.get("queryStringParameters", {}) or {}

    def _parse_event_body(self) -> Dict[str, Any]:
        """Parse the event body as JSON with proper validation.

        This method safely parses the event body, handling various edge cases
        including empty bodies, invalid JSON, and non-dictionary results.

        Returns:
            A dictionary parsed from the event body, or an empty dict if parsing fails.
        """
        body = self.event.get("body")

        # Handle None or empty body
        if body is None:
            return {}

        # Handle empty string
        if isinstance(body, str) and not body.strip():
            return {}

        try:
            result = Serializer.json_loads(body)

            # Ensure result is a dictionary
            if not isinstance(result, dict):
                self.logger.warning(
                    f"Event body parsed to non-dictionary type: {type(result).__name__}"
                )
                return {}

            return result
        except (ValueError, TypeError) as e:
            self.logger.debug(f"Failed to parse event body as JSON: {e}")
            return {}
        except Exception as e:
            self.logger.warning(f"Unexpected error parsing event body: {e}")
            return {}

    def _get_api_key(self) -> str:
        def is_valid_api_key(value: Optional[str]) -> bool:
            return bool(value and str(value).strip())

        api_key = self.event.get("requestContext", {}).get("identity", {}).get("apiKey")

        if is_valid_api_key(value=api_key):
            return api_key.strip()

        # Event root: api_key
        api_key = self.event.get("api_key")

        if is_valid_api_key(value=api_key):
            return str(api_key).strip()

        # Request header: x-api-key / api-key
        api_key = (
            self._get_header("x-api-key")
            or self._get_header("api-key")
            or self._get_header("x_api_key")
            or self._get_header("api_key")
        )

        if is_valid_api_key(value=api_key):
            return str(api_key).strip()

        # QueryString: api_key
        api_key = (
            self._get_query_string_parameter("api_key")
            or self._get_query_string_parameter("api-key")
            or self._get_query_string_parameter("x_api_key")
            or self._get_query_string_parameter("x-api-key")
        )

        if is_valid_api_key(value=api_key):
            return str(api_key).strip()

        # Body: api_key
        api_key = self._parse_event_body().get("api_key")

        if is_valid_api_key(value=api_key):
            return str(api_key).strip()

        return "#####"

    def _get_authorize_function_name(self) -> str:
        return self.setting.get("authorizer_authorize_function_name") or "authorize"

    def _get_verify_permission_function_name(self) -> str:
        return (
            self.setting.get("authorizer_verify_permission_function_name")
            or "verify_permission"
        )

    def _get_authorized_user(self) -> Dict[str, Any]:
        return self.event.get("requestContext", {}).get("authorizer") or {}

    def _get_proxied_callable(
        self,
        module_name: str,
        class_name: Optional[str],
        function_name: Optional[str],
    ) -> Callable:
        """Get a proxied callable with caching for performance optimization.

        This method uses a class-level cache to avoid repeated module resolution
        and class instantiation, significantly improving performance for
        frequently accessed handlers.

        Args:
            module_name: The module name to resolve.
            class_name: The class name within the module (optional).
            function_name: The function name to call (optional).

        Returns:
            A callable that can be invoked.

        Raises:
            Exception: If the callable cannot be resolved.
        """
        # Create a unique cache key based on all parameters
        cache_key = f"{module_name}:{class_name or ''}:{function_name or ''}"

        # Check cache first
        if cache_key in self._callable_cache:
            self.logger.debug(f"Cache hit for callable: {cache_key}")
            return self._callable_cache[cache_key]

        try:
            callable_obj = Invoker.resolve_proxied_callable(
                module_name=module_name,
                class_name=class_name,
                function_name=function_name,
                constructor_parameters={"logger": self.logger, **self.setting},
            )
            # Store in cache for future use
            self._callable_cache[cache_key] = callable_obj
            self.logger.debug(f"Cached callable: {cache_key}")
            return callable_obj
        except Exception:
            raise

    def _get_lambda_function_invoker(
        self,
        payload: Dict[str, Any],
        function_name: Optional[str] = None,
        invocation_type: InvocationType = InvocationType.EVENT,
    ) -> Any:
        if not function_name:
            function_name = self.context.function_name

        return self.__class__.invoke_aws_lambda_function(
            function_name=function_name,
            payload=payload,
            invocation_type=invocation_type,
            qualifier=self.context.function_version,
        )

    def _get_metadata(self, endpoint_id: Optional[str] = None) -> Dict[str, Any]:
        metadata = {
            "plugin_context": self.get_plugin_context(),
            "aws_lambda_invoker": self._get_lambda_function_invoker,
            "aws_lambda_context": self.context,
            "graphql_schema_picker": GraphqlSchemaModel.get_schema_picker(
                endpoint_id or self._get_endpoint_id()
            ),
        }
        extra = self._extract_additional_parameters(
            {
                **self._get_headers(),
                **self._get_path_parameters(),
                **self._get_query_string_parameters(),
            }
        )

        if isinstance(extra, dict) and len(extra) > 0:
            metadata.update(extra)

        return metadata

    def _validate_required_string(
        self,
        value: Any,
        field_name: str,
        max_length: Optional[int] = None,
    ) -> str:
        """Validate a required string field."""
        if value is None:
            raise ValueError(f"{field_name} is required")

        value = str(value).strip()

        if not value:
            raise ValueError(f"{field_name} cannot be empty")

        if max_length and len(value) > max_length:
            raise ValueError(f"{field_name} exceeds maximum length of {max_length}")

        return value

    def _validate_optional_string(
        self,
        value: Any,
        field_name: str,
        max_length: Optional[int] = None,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """Validate an optional string field."""
        if value is None:
            return default

        value = str(value).strip()

        if not value:
            return default

        if max_length and len(value) > max_length:
            raise ValueError(f"{field_name} exceeds maximum length of {max_length}")

        return value

    def _validate_dict(
        self,
        value: Any,
        field_name: str,
        required: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Validate a dictionary field."""
        if value is None:
            if required:
                raise ValueError(f"{field_name} is required")
            return None

        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a dictionary")

        return value

    def _validate_list(
        self,
        value: Any,
        field_name: str,
        required: bool = False,
        min_length: Optional[int] = None,
    ) -> Optional[List[Any]]:
        """Validate a list field."""
        if value is None:
            if required:
                raise ValueError(f"{field_name} is required")
            return None

        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")

        if min_length is not None and len(value) < min_length:
            raise ValueError(f"{field_name} must have at least {min_length} items")

        return value

    def _extract_core_parameters(self) -> Tuple[str, str, Dict[str, Any]]:
        """Extract and organize event-related data."""
        api_key = self._get_api_key()
        area = self._get_api_area()

        if not area:
            raise ValueError("`area` is required in path parameters")

        endpoint_id = self._get_endpoint_id()

        if not endpoint_id:
            raise ValueError("`endpoint_id` is required in path parameters")

        parameters = {
            **self._parse_event_body(),
            **self._get_query_string_parameters(),
            "endpoint_id": endpoint_id,
            "area": area,
            "api_key": api_key,
            "stage": self._get_api_stage(),
            "metadata": self._get_metadata(endpoint_id=endpoint_id),
        }

        return (
            api_key,
            endpoint_id,
            parameters,
        )

    def _extract_additional_parameters(
        self,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract additional parameters from the metadata."""
        result = {}

        if not isinstance(metadata, dict) or len(metadata) < 1:
            return result

        keys = self.setting.get("custom_header_keys", [])

        # Parse header keys
        if isinstance(keys, str):
            try:
                keys = Serializer.json_loads(keys)
            except Exception:
                keys = [key for key in keys.split(",")]
        elif not isinstance(keys, list):
            keys = []

        if not keys:
            return result

        # Pre-convert header keys to snake_case for comparison
        snake_case_keys = {
            Utility.to_snake_case(key.strip()): key
            for key in keys
            if isinstance(key, str) and key.strip()
        }
        snake_case_keys_len = len(snake_case_keys)

        if snake_case_keys_len == 0:
            return result

        # Process only needed headers, converting keys on-the-fly
        for original_key, value in metadata.items():
            if snake_case_keys_len == len(result):
                break

            snake_key = Utility.to_snake_case(original_key)

            if snake_key in snake_case_keys:
                result[snake_key] = value

        return result

    def _get_default_setting_index(self) -> str:
        return (
            f"{self._get_api_stage()}_{self._get_api_area()}_{self._get_endpoint_id()}"
        )

    def _initialize(self) -> "Handler":
        # Get default setting
        if not self.setting:
            self.setting = ConfigModel.find(
                setting_id=self._get_default_setting_index(),
                return_dict=True,
            )

        return self

    def set_plugin_context(self, context: PluginContext):
        """Set plugin context for backward compatibility."""
        if isinstance(context, dict):
            set_current_plugin_context(context)
        elif hasattr(context, "get"):
            set_current_plugin_context(context)

    def get_plugin_context(self) -> Optional[PluginContext]:
        """Get plugin context for backward compatibility."""
        return get_current_plugin_context()
