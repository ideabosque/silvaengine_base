#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from .lambdabase import LambdaBase
from typing import Any, Dict, Tuple
from silvaengine_utility import Utility, Authorizer as ApiGatewayAuthorizer
import os, traceback, pendulum

__author__ = "bibow"

FULL_EVENT_AREAS = os.environ.get("FULL_EVENT_AREAS", "").split(",")

class Resources(LambdaBase):
    settings: Dict[str, Any] = {}

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    def handle(self, event: Dict[str, Any], context: Any) -> Any:
        try:
            # Check if the event is from a WebSocket connection
            request_context = event.get("requestContext", {})
            connection_id = request_context.get("connectionId")
            route_key = request_context.get("routeKey")

            if connection_id and route_key:
                return self._handle_websocket_event(
                    event, context, connection_id, route_key
                )

            # If it's not a WebSocket event, handle it as a regular API request
            return self._handle_http_request(event, context)
        except Exception as e:
            return self._handle_exception(e, event)

    def _handle_websocket_event(
        self, event: Dict[str, Any], context: Any, connection_id: str, route_key: str
    ) -> Dict[str, Any]:
        """
        Handle WebSocket connection events including connection, disconnection, and streaming.
        """
        if route_key == "$connect":
            if self._is_authorization_event(event):
                return self._handle_authorize(event, context, "authorize")

            endpoint_id = event.get("queryStringParameters", {}).get("endpointId")
            area = event.get("queryStringParameters", {}).get("area", "")
            api_key = event.get("requestContext", {}).get("identity", {}).get("apiKey")
            api_key = (
                event.get("queryStringParameters", {}).get("x-api-key")
                if api_key is None
                else api_key
            )

            if api_key is not None and endpoint_id is not None:
                LambdaBase.save_wss_connection(
                    endpoint_id=endpoint_id,
                    connection_id=connection_id,
                    area=area,
                    api_key=api_key,
                    data=event.get("requestContext", {}).get("authorizer", {})
                )
                LambdaBase.remove_expired_connections(
                    endpoint_id,
                    event.get("requestContext", {}).get("authorizer", {}).get("email"),
                )

            return {"statusCode": 200, "body": "Connection successful"}

        elif route_key == "$disconnect":
            results = LambdaBase.get_wss_connections(connection_id)
            wss_onnections = [result for result in results]

            if len(wss_onnections) > 0:
                wss_onnections[0].status = "inactive"
                wss_onnections[0].updated_at = pendulum.now("UTC")
                wss_onnections[0].save()

            return {"statusCode": 200, "body": "Disconnection successful"}

        elif route_key == "stream":
            return self._handle_websocket_stream(event, context)

        self.logger.warning(f"Invalid WebSocket route: {route_key}")
        return {"statusCode": 400, "body": "Invalid WebSocket route"}

    def _handle_websocket_stream(
        self, event: Dict[str, Any], context: Any
    ) -> Dict[str, Any]:
        """
        Process the 'stream' route for WebSocket events, managing the payload and dispatching tasks.
        """
        connection_id = event.get("requestContext", {}).get("connectionId")
        request_context = event.get("requestContext", {})
        api_key = request_context.get("identity", {}).get("apiKey")
        results = LambdaBase.get_wss_connections(connection_id)

        if not results:
            self.logger.error("WebSocket connection not found")
            return {"statusCode": 404, "body": "WebSocket connection not found"}

        wss_onnections = [result for result in results]
        endpoint_id = wss_onnections[0].endpoint_id

        if api_key is None:
            api_key = wss_onnections[0].api_key

        body = (
            Utility.json_loads(event.get("body"))
            if event.get("body") is not None
            else {}
        )

        funct = body.get("funct")
        params = (
            Utility.json_loads(body.get("payload"))
            if body.get("payload") is not None
            else {}
        )
        params["endpoint_id"] = endpoint_id

        if not endpoint_id or not funct:
            self.logger.error(
                "Missing 'endpointId' or 'funct' in the stream payload"
            )
            return {
                "statusCode": 400,
                "body": "Missing required parameters: endpointId or funct",
            }

        method = self._get_http_method(event)
        setting, function = LambdaBase.get_function(
            endpoint_id, funct, api_key=api_key, method=method
        )

        return self._invoke_function(event, context, function, params, setting)

    def _handle_http_request(
        self, event: Dict[str, Any], context: Any
    ) -> Dict[str, Any]:
        """
        Process regular HTTP API requests when the event is not related to WebSocket.
        """
        if not self.settings:
            self._initialize(event)

        if self._is_cognito_trigger(event):
            return self._handle_cognito_trigger(event, context)
        
        api_key, endpoint_id, function_name, params = self._extract_event_data(event)
        path_parameters = event.get("pathParameters", {})
        request_context = event.get("requestContext", {})
        method = self._get_http_method(event)
        setting, function = LambdaBase.get_function(
            endpoint_id, function_name, api_key=api_key, method=method
        )

        self._validate_function_area(params, function)
        event.update(
            self._prepare_event(
                event.get("headers", {}),
                path_parameters.get("area"),
                request_context,
                function,
                endpoint_id,
            )
        )

        # Add authorization for http event
        auth_required = bool(function and function.config and function.config.auth_required)

        if self._is_authorization_event(event):
            if auth_required:
                try:
                    return self._handle_authorize(
                        event, 
                        context, 
                        self.settings.get("authorizer_authorize_function_name", "authorize")
                    )
                except Exception as e:
                    raise e

            return ApiGatewayAuthorizer(event).authorize(is_allow=True)
        
        if event.get("body") and auth_required:
            event.update(
                self._handle_authorize(
                    event, 
                    context, 
                    self.settings.get("authorizer_verify_permission_function_name", "verify_permission")
                )
            )

        return self._invoke_function(event, context, function, params, setting)

    def _extract_event_data(
        self, event: Dict[str, Any]
    ) -> Tuple[str, str, str, Dict[str, Any]]:
        """Extract and organize event-related data."""
        if not isinstance(event, dict):
            raise ValueError("Event must be a dictionary")

        # headers = event.get("headers", {}) or {}
        request_context = event.get("requestContext", {}) or {}
        path_parameters = event.get("pathParameters", {}) or {}
        identity = request_context.get("identity", {}) or {}
        api_key = identity.get("apiKey", "#####")
        area = path_parameters.get("area")

        if not area:
            raise ValueError("`area` is required in path parameters")

        endpoint_id = path_parameters.get("endpoint_id", "")

        if not endpoint_id:
            raise ValueError("`endpoint_id` is required in path parameters")

        proxy = path_parameters.get("proxy", "")

        if not proxy:
            raise ValueError("`proxy` is required in path parameters")

        query_params = event.get("queryStringParameters")

        if query_params is None:
            query_params = {}

        function_name = proxy.split("/")[0] if proxy else ""

        if not function_name:
            raise ValueError("missing `function_name` in request")

        if "/" in proxy:
            path = proxy.split("/", 1)[1]
            query_params["path"] = path

        params = {k: v for k, v in query_params.items()}
        params["endpoint_id"] = endpoint_id
        params["area"] = area

        headers = event.get("headers")

        if headers is Dict:
            params.update({
                "custom_headers": self._extract_event_headers(headers)
            })

        return api_key, endpoint_id, function_name, params
    
    def _extract_event_headers(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        """Extract custom headers from the event."""
        headers = {Utility.to_snake_case(k):v for k,v in headers.items()}
        result = {}

        for key in self.settings.get("custom_header_keys", []):
            key = Utility.to_snake_case(key)
            result[key] = headers.get(key,"")
        
        return result

    def _handle_cognito_trigger(self, event: Dict[str, Any], context: Any) -> Any:
        """Handle Cognito triggers."""
        if not self.settings:
            self._initialize(event)

        return Utility.import_dynamically(
            module_name=self.settings.get("cognito_hook_module_name", "event_triggers"),
            function_name=self.settings.get("cognito_hook_function_name", "pre_token_generate"),
            class_name=self.settings.get("cognito_hook_class_name", "Cognito"),
            constructor_parameters={"logger": self.logger, **self.settings},
        )(event, context)

    def _get_http_method(self, event: Dict[str, Any]) -> str:
        """Get the HTTP method from the event."""
        return event.get("requestContext", {}).get(
            "httpMethod", event.get("httpMethod", "POST")
        )

    def _validate_function_area(self, params: Dict[str, Any], function: Any) -> None:
        """Validate if the area matches the function configuration."""
        area = params.get("area")
        assert area == function.area, (
            f"Area ({area}) does not match the function ({function.area})."
        )

    def _prepare_event(
        self,
        header: Dict[str, Any],
        area: str,
        request_context: Dict[str, Any],
        function: Any,
        endpoint_id: str,
    ) -> Dict[str, Any]:
        """Prepare the event data for function invocation."""
        request_context.update(
            {
                "channel": endpoint_id,
                "area": area,
                "headers": header,
            }
        )

        return {
            "fnConfigurations": Utility.json_loads(Utility.json_dumps(function)),
            "requestContext": request_context,
            "module": function.config.module_name,
            "class": function.config.class_name,
            "function": function.function,
        }

    def _handle_authorize(self, event: Dict[str, Any], context: Any, action: str) -> Any:
        """Dynamically handle authorization and permission checks."""
        fn = Utility.import_dynamically(
            module_name=self.settings.get("authorizer_module_name", "silvaengine_authorizer"),
            function_name=action,
            class_name=self.settings.get("authorizer_class_name", "Authorizer"),
            constructor_parameters={"logger": self.logger, **self.settings},
        )

        if callable(fn):
            if action == self.settings.get("authorizer_authorize_function_name", "authorize"):
                return fn(event, context)
            elif action == self.settings.get("authorizer_verify_permission_function_name", "verify_permission"):
                return fn(event, context)

    def _invoke_function(
        self,
        event: Dict[str, Any],
        context: Any,
        function: Any,
        params: Dict[str, Any],
        setting: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke the appropriate function based on event data."""
        if str(event.get("requestContext")).strip().upper() == "POST":
            params.update(Utility.json_loads(event.get("requestContext")))

        if event.get("body"):
            params.update(Utility.json_loads(event.get("body")))

        return Utility.import_dynamically(
            module_name=function.config.module_name,
            function_name=function.function,
            class_name=function.config.class_name,
            constructor_parameters={"logger": self.logger, **setting},
        )(**params)

    def _handle_exception(
        self, exception: Exception, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle and log exceptions."""
        status_code = 500
        message = traceback.format_exc()
        self.logger.exception(message)

        if exception.args:
            message = exception.args[0]

            if len(exception.args) > 1 and isinstance(exception.args[1], int):
                status_code = exception.args[1]

        if self._is_authorization_event(event):
            return ApiGatewayAuthorizer(event).authorize(is_allow=False, context={"errorMessage": str(message)})

        return self._generate_response(status_code, str(message))
    
    def _generate_response(self, status_code: int, body: str) -> Dict[str, Any]:
        """Generate a standard HTTP response."""
        return {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": body
        }

    def _is_authorization_event(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a request event."""
        return bool(str(event.get("type")).strip().upper() in ["REQUEST", "TOKEN"])

    def _is_cognito_trigger(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a Cognito trigger."""
        return bool(event.get("triggerSource") and event.get("userPoolId"))
    
    def _get_setting_index(self, event: Dict[str, Any]) -> str:
        """Get the appropriate setting index based on the event data."""
        if self._is_cognito_trigger(event):
            settings = LambdaBase.get_setting("general")
            return settings.get(event.get("userPoolId", ""), "")
        elif event.get("requestContext") and event.get("pathParameters"):
            request_context, path_parameters = (
                event.get("requestContext", {}),
                event.get("pathParameters", {}),
            )
            return f"{request_context.get('stage', 'beta')}_{path_parameters.get('area')}_{path_parameters.get('endpoint_id')}"
        raise ValueError("Invalid event request")

    def _initialize(self, event: Dict[str, Any]) -> None:
        """Load settings from configuration data."""
        self.settings = LambdaBase.get_setting(self._get_setting_index(event))
