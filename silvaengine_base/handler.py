#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import boto3
from silvaengine_constants import (
    AuthorizationAction,
    AuthorizationType,
    HttpStatus,
    InvocationType,
    RequestMethod,
)
from silvaengine_dynamodb_base.models import (
    ConfigModel,
    ConnectionModel,
    FunctionModel,
)
from silvaengine_utility import (
    Authorizer,
    Debugger,
    HttpResponse,
    Invoker,
    Serializer,
    Utility,
)


class Handler:
    region = os.getenv("REGION_NAME", os.getenv("REGIONNAME", "us-east-1"))
    aws_lambda = boto3.client("lambda", region_name=region)

    def __init__(
        self,
        event: Dict[str, Any],
        context: Any,
        logger: logging.Logger,
    ) -> None:
        self.logger = (
            logger
            if isinstance(logger, logging.Logger)
            else logging.getLogger(__name__)
        )
        self.event = event or {}
        self.context = context
        self.setting = {}

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
        logger: logging.Logger,
    ):
        if cls.is_event_match_handler(event):
            return cls(
                logger=logger,
                event=event,
                context=context,
            )._initialize()
        return None

    @classmethod
    def _generate_response(cls, status_code: int, body: Any) -> Dict[str, Any]:
        """Generate a standard HTTP response."""
        return HttpResponse.format_response(
            status_code=HttpStatus.INTERNAL_SERVER_ERROR.value,
            data=body,
        )

    def _merge_setting_to_default(self, setting: Dict[str, Any]):
        if type(setting) is dict:
            self.setting.update(setting)
        return self

    def _merge_metadata_to_event(self, metadata: Any):
        if type(metadata) is dict:
            self.event.update(metadata)
        return self

    def _invoke_authorization(self, action: AuthorizationAction) -> Any:
        """Dynamically handle authorization and permission checks."""
        try:
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
        except Exception as e:
            raise e

    @classmethod
    def invoke_aws_lambda_function(
        cls,
        function_name: str,
        payload: dict,
        invocation_type: InvocationType = InvocationType.EVENT,
    ) -> Any:
        """
        Invoke another Lambda function.
        :param function_name: Name of the Lambda function to invoke.
        :param payload: The payload to send to the Lambda function.
        :param invocation_type: Invocation type, default is "Event".
        :return: The response of the invoked Lambda function.
        """
        if not function_name:
            raise ValueError("Function name is required")
        elif not payload:
            payload = {}

        valid_invocation_types = {
            InvocationType.EVENT,
            InvocationType.REQUEST_RESPONSE,
            InvocationType.DRY_RUN,
        }

        if invocation_type not in valid_invocation_types:
            raise ValueError(f"Invalid invocation_type: {invocation_type.value}")

        try:
            function_payload = Serializer.json_dumps(payload, separators=(",", ":"))
            response = cls.aws_lambda.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=function_payload,
            )

            if "Payload" not in response:
                raise Exception("Invalid response structure")
            elif invocation_type == "RequestResponse":
                try:
                    payload_content = response["Payload"].read()

                    return (
                        Serializer.json_loads(payload_content)
                        if payload_content
                        else {}
                    )
                except Exception as e:
                    raise e
        except Exception as e:
            raise e

    @classmethod
    def _get_function_and_setting(
        cls,
        endpoint_id: str,
        function_name: str,
        api_key: str = "#####",
        method: str | None = None,
    ) -> Tuple[Dict[str, Any], FunctionModel]:
        """
        Fetch the function configuration for a given endpoint.
        :param endpoint_id: ID of the endpoint.
        :param function_name: Name of the function to retrieve.
        :param api_key: The API key, default is "#####".
        :param method: The HTTP method if applicable.
        :return: A tuple containing the merged settings and the function object.
        """
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
                    f"Cannot find the function({function_name}) with endpoint_id({endpoint_id}) and api_key({api_key})."
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
        return (
            self.event["requestContext"].get("http", {}).get("method")
            or self.event["requestContext"]["httpMethod"]
        )

    def _get_endpoint_id(self) -> str:
        return (
            self.event.get("pathParameters", {}).get("endpoint_id")
            or str(self.context.function_name).split("_")[0].strip().lower()
        )

    def _get_api_stage(self) -> str:
        return self.event["requestContext"].get("stage") or "beta"

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

    def _get_header(self, key: str) -> str:
        return self.event.get("headers", {}).get(str(key).strip())

    def _get_query_string_parameter(self, key: str) -> str:
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
        try:
            return Serializer.json_loads(self.event.get("body", "{}"))
        except Exception:
            pass
        return {}

    def _get_api_key(self) -> str:
        def is_valid_api_key(value: Optional[str]) -> bool:
            return bool(value and str(value).strip())

        api_key = self.event["requestContext"].get("identity", {}).get("apiKey")

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
        return self.event["requestContext"].get("authorizer") or {}

    def _get_proxied_callable(
        self,
        module_name: str,
        class_name: str,
        function_name: str,
    ) -> Callable:
        try:
            return Invoker.resolve_proxied_callable(
                module_name=module_name,
                class_name=class_name,
                function_name=function_name,
                constructor_parameters={"logger": self.logger, **self.setting},
            )
        except Exception as e:
            raise e

    def _extract_core_parameters(self) -> Tuple[str, str, str, Dict[str, Any]]:
        """Extract and organize event-related data."""
        api_key = self._get_api_key()
        area = self._get_api_area()

        if not area:
            raise ValueError("`area` is required in path parameters")

        endpoint_id = self._get_endpoint_id()

        if not endpoint_id:
            raise ValueError("`endpoint_id` is required in path parameters")

        metadata = self._extract_additional_parameters(
            {
                **self._get_headers(),
                **self._get_path_parameters(),
                **self._get_query_string_parameters(),
            }
        )
        metadata.update(aws_lambda_invoker=self.__class__.invoke_aws_lambda_function)

        parameters = {
            **self._get_query_string_parameters(),
            "endpoint_id": endpoint_id,
            "area": area,
            "api_key": api_key,
            "metadata": metadata,
        }
        parameters.update(**self._parse_event_body())

        function_name, proxy_path = self._get_proxy_function_and_path()

        if not function_name:
            raise ValueError("missing `function_name` in request")
        elif proxy_path:
            parameters.update(path=proxy_path)

        return (
            api_key,
            endpoint_id,
            function_name,
            parameters,
        )

    def _extract_additional_parameters(
        self,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract additional parameters from the metadata."""
        result = {}

        if type(metadata) is not dict or len(metadata) < 1:
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
            Utility.to_snake_case(key.strip()): key for key in keys if key.strip()
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

    def _initialize(self) -> Any:
        # Get default setting
        if not self.setting:
            self.setting = ConfigModel.find(
                setting_id=self._get_default_setting_index(),
                return_dict=True,
            )

        return self
