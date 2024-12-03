#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import traceback
from datetime import datetime
from typing import Any, Dict, Tuple

import jsonpickle
import pendulum
import sentry_sdk
import yaml
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

from silvaengine_base.lambdabase import FunctionError, LambdaBase
from silvaengine_utility import Authorizer as ApiGatewayAuthorizer
from silvaengine_utility import Utility

from .models import WSSConnectionModel

__author__ = "bibow"


class Resources(LambdaBase):
    settings: Dict[str, Any] = {}

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    def handle(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        try:
            # Check if the event is from a WebSocket connection
            request_context = event.get("requestContext", {})
            connection_id = request_context.get("connectionId")
            route_key = request_context.get("routeKey")

            if connection_id and route_key:
                self.logger.info(f"WebSocket event received: {event}")
                return self._handle_websocket_event(
                    context, event, connection_id, route_key
                )

            # If it's not a WebSocket event, handle it as a regular API request
            return self._handle_http_request(event, context)
        except Exception as e:
            return self._handle_exception(e, event)

    def _handle_websocket_event(
        self, context: Any, event: Dict[str, Any], connection_id: str, route_key: str
    ) -> Dict[str, Any]:
        """
        Handle WebSocket connection events including connection, disconnection, and streaming.
        """
        if route_key == "$connect":
            self.logger.info(f"WebSocket connected: {connection_id}")

            # if event.get("requestContext", {}).get("authorizer") is not None:
            #     return {"statusCode": 200, "body": "Connection successful"}
            result = {"statusCode": 200, "body": "Connection successful"}

            if self._is_request_event(event):
                result = self._dynamic_authorization(event, context, "authorize")

            endpoint_id = event.get("queryStringParameters", {}).get("endpointId")
            area = event.get("queryStringParameters", {}).get("area", "")
            api_key = event.get("requestContext", {}).get("identity", {}).get("apiKey")
            api_key = (
                event.get("queryStringParameters", {}).get("x-api-key")
                if api_key is None
                else api_key
            )
            
            if api_key is not None and endpoint_id is not None:
                WSSConnectionModel(
                    endpoint_id,
                    connection_id,
                    **{
                        "api_key": api_key,
                        "area": area,
                        "data": result.get("context",{}),
                        "updated_at": pendulum.now("UTC"),
                        "created_at": pendulum.now("UTC"),
                    },
                ).save()

            return result

        elif route_key == "$disconnect":
            self.logger.info(f"WebSocket disconnected: {connection_id}")

            results = WSSConnectionModel.connect_id_index.query(connection_id, None)

            if not results:
                wss_onnections = [result for result in results]
                wss_onnections[0].status = "inactive"
                wss_onnections[0].updated_at = pendulum.now("UTC")
                wss_onnections[0].save()

                self._delete_expired_connections(
                    wss_onnections[0].endpoint_id, wss_onnections[0].data.get("email")
                )

            return {"statusCode": 200, "body": "Disconnection successful"}

        elif route_key == "stream":
            return self._handle_websocket_stream(event)

        self.logger.warning(f"Invalid WebSocket route: {route_key}")
        return {"statusCode": 400, "body": "Invalid WebSocket route"}

    def _handle_websocket_stream(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the 'stream' route for WebSocket events, managing the payload and dispatching tasks.
        """
        try:
            #########################################
            # Add authorization for websocket event #
            #########################################

            connection_id = event.get("requestContext", {}).get("connectionId")
            request_context = event.get("requestContext", {})
            api_key = request_context.get("identity", {}).get("apiKey")
            results = WSSConnectionModel.connect_id_index.query(connection_id, None)
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
            self.logger.info(f"WebSocket stream received: {body}")

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

            return self._invoke_function(event, function, params, setting)
        except Exception as e:
            self.logger.error(f"Error processing WebSocket stream: {str(e)}")
            return {"statusCode": 500, "body": "Internal Server Error"}

    def _handle_http_request(
        self, event: Dict[str, Any], context: Any
    ) -> Dict[str, Any]:
        """
        Process regular HTTP API requests when the event is not related to WebSocket.
        """
        api_key, endpoint_id, funct, params = self._extract_event_data(event)
        self._initialize_settings(event)

        if self._is_cognito_trigger(event):
            return self._handle_cognito_trigger(event, context)

        path_parameters = event.get("pathParameters", {})
        request_context = event.get("requestContext", {})
        method = self._get_http_method(event)
        setting, function = LambdaBase.get_function(
            endpoint_id, funct, api_key=api_key, method=method
        )

        self._validate_function_area(params, function)
        self.logger.info(f"HTTP event received: {event}")
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
        if self._is_request_event(event):
            # Authorization
            return self._dynamic_authorization(event, context, "authorize")
        if event.get("body"):
            event.update(
                self._dynamic_authorization(event, context, "verify_permission")
            )

        return self._invoke_function(event, function, params, setting)

    def _delete_expired_connections(self, endpoint_id, email):
        # Calculate the cutoff time using pendulum
        cutoff_time = pendulum.now("UTC").subtract(days=1)

        filter_condition = None
        if email is None:
            return

        filter_condition &= WSSConnectionModel.updated_at < cutoff_time
        filter_condition &= WSSConnectionModel.data.email.exists
        filter_condition &= WSSConnectionModel.data.email == email

        # Query connections with filters
        connections = WSSConnectionModel.query(
            endpoint_id,
            None,  # Range key condition
            filter_condition=filter_condition,
        )

        # Iterate through and delete matching connections
        for connection in connections:
            print(
                f"Deleting connection: endpoint_id={connection.endpoint_id}, connection_id={connection.connection_id}"
            )
            connection.delete()

    def _initialize_settings(self, event: Dict[str, Any]) -> None:
        """Initialize settings and log start time."""
        if not self.settings:
            self.init(event)

    def _extract_event_data(
        self, event: Dict[str, Any]
    ) -> Tuple[str, str, str, Dict[str, Any]]:
        """Extract and organize event-related data."""
        headers = event.get("headers", {})
        request_context = event.get("requestContext", {})
        path_parameters = event.get("pathParameters", {})

        api_key = request_context.get("identity", {}).get("apiKey")
        area = path_parameters.get("area")
        endpoint_id = path_parameters.get("endpoint_id")
        proxy = path_parameters.get("proxy", "")
        query_params = event.get("queryStringParameters", {}) or {}

        funct, _, path = proxy.partition("/")
        if path:
            query_params["path"] = path

        params = {**query_params, "endpoint_id": endpoint_id, "area": area}

        proxy_index = str(self.settings.get("api_unified_call_index", "")).strip()
        funct = headers.get(proxy_index, funct).strip()

        return api_key, endpoint_id, funct, params

    def _runtime_debug(self, endpoint_id: str, start_time: int, mark: str) -> int:
        """Log the execution time for debugging."""
        duration = int(datetime.now().timestamp() * 1000) - start_time

        if not endpoint_id:
            print(f"Warning: `endpoint_id` is missing when executing `{mark}`.")

        if endpoint_id and endpoint_id.strip().lower() == "ss3" and duration > 0:
            print(f"--------- It took {duration} ms to execute request `{mark}`.")

        return int(datetime.now().timestamp() * 1000)

    def _is_cognito_trigger(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a Cognito trigger."""
        return bool(event.get("triggerSource") and event.get("userPoolId"))

    def _handle_cognito_trigger(self, event: Dict[str, Any], context: Any) -> Any:
        """Handle Cognito triggers."""
        result = Utility.import_dynamically(
            module_name=self.settings.get(
                "cognito_hooks_module_name", "event_triggers"
            ),
            function_name=self.settings.get(
                "cognito_hooks_function_name", "pre_token_generate"
            ),
            class_name=self.settings.get("cognito_hooks_class_name", "Cognito"),
            constructor_parameters={"logger": self.logger, **self.settings},
        )(event, context)
        return result

    def _get_http_method(self, event: Dict[str, Any]) -> str:
        """Get the HTTP method from the event."""
        return event.get("requestContext", {}).get(
            "httpMethod", event.get("httpMethod", "POST")
        )

    def _validate_function_area(self, params: Dict[str, Any], function: Any) -> None:
        """Validate if the area matches the function configuration."""
        area = params.get("area")
        assert (
            area == function.area
        ), f"Area ({area}) does not match the function ({function.area})."

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
        }

    def _dynamic_authorization(
        self, event: Dict[str, Any], context: Any, action: str
    ) -> Any:
        """Dynamically handle authorization and permission checks."""
        try:
            fn = Utility.import_dynamically(
                module_name="silvaengine_authorizer",
                function_name=action,
                class_name="Authorizer",
                constructor_parameters={"logger": self.logger},
            )

            if callable(fn):
                if action == "authorize":
                    return fn(event, context)
                elif action == "verify_permission":
                    return fn(event, context)
        except Exception as e:
            raise e

    def _invoke_function(
        self,
        event: Dict[str, Any],
        function: Any,
        params: Dict[str, Any],
        setting: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke the appropriate function based on event data."""
        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": json.dumps(setting),
            "params": json.dumps(params),
            "body": event.get("body"),
            "context": jsonpickle.encode(
                event.get("requestContext"), unpicklable=False
            ),
        }

        if function.config.funct_type.strip().lower() == "event":
            LambdaBase.invoke(function.aws_lambda_arn, payload, invocation_type="Event")
            return self._generate_response(200, "")

        result = LambdaBase.invoke(
            function.aws_lambda_arn,
            payload,
            invocation_type=function.config.funct_type.strip(),
        )
        return self._process_response(result)

    def _generate_response(self, status_code: int, body: str) -> Dict[str, Any]:
        """Generate a standard HTTP response."""
        return {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": body,
        }

    def _process_response(self, result: Any) -> Dict[str, Any]:
        """Process the result and format the response."""
        response = self._generate_response(200, result)
        if self._is_json(result):
            response["statusCode"] = 200
        elif isinstance(result, FunctionError):
            response.update(
                {"statusCode": 500, "body": f'{{"error": "{result.args[0]}"}}'}
            )
        elif self._is_yaml(result):
            response["headers"]["Content-Type"] = "application/x-yaml"
        else:
            response.update(
                {"statusCode": 400, "body": '{"error": "Unsupported content format"}'}
            )
        return response

    def _handle_exception(
        self, exception: Exception, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle and log exceptions."""
        log = traceback.format_exc()
        self.logger.exception(log)

        message = exception.args[0] if exception.args else log
        status_code = (
            exception.args[1]
            if len(exception.args) > 1 and isinstance(exception.args[1], int)
            else 500
        )

        if self._is_request_event(event):
            return self._handle_authorizer_failure(event, message)

        if str(status_code).startswith("5") and self.settings.get(
            "sentry_enabled", False
        ):
            sentry_sdk.capture_exception(exception)

        return self._generate_error_response(status_code, message)

    def _handle_authorizer_failure(
        self, event: Dict[str, Any], message: str
    ) -> Dict[str, Any]:
        """Handle API Gateway authorizer failure."""
        arn, request_context = event.get("methodArn", ""), event.get(
            "requestContext", {}
        )
        return ApiGatewayAuthorizer(
            principal=event.get("path"),
            aws_account_id=request_context.get("accountId"),
            api_id=request_context.get("apiId"),
            region=arn.split(":")[3],
            stage=request_context.get("stage"),
        ).authorize(is_allow=False, context={"error_message": message})

    def _generate_error_response(
        self, status_code: int, message: str
    ) -> Dict[str, Any]:
        """Generate a standardized error response."""
        return {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": message}),
        }

    def _is_request_event(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a request event."""
        return bool(str(event.get("type")).strip().lower() == "request")

    @staticmethod
    def _is_json(content: Any) -> bool:
        """Check if the content is valid JSON."""
        try:
            json.loads(content)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_yaml(content: Any) -> bool:
        """Check if the content is valid YAML."""
        try:
            yaml.load(content, Loader=yaml.SafeLoader)
            return True
        except yaml.YAMLError:
            return False

    def get_setting_index(self, event: Dict[str, Any]) -> str:
        """Get the appropriate setting index based on the event data."""
        try:
            if event.get("triggerSource") and event.get("userPoolId"):
                settings = LambdaBase.get_setting("general")
                return settings.get(event.get("userPoolId"))
            elif event.get("requestContext") and event.get("pathParameters"):
                request_context, path_parameters = event.get(
                    "requestContext", {}
                ), event.get("pathParameters", {})
                return f"{request_context.get('stage', 'beta')}_{path_parameters.get('area')}_{path_parameters.get('endpoint_id')}"
        except Exception as e:
            raise Exception(f"Invalid event request: {e}")

    def init(self, event: Dict[str, Any]) -> None:
        """Load settings from configuration data and initialize Sentry if enabled."""
        self.settings = LambdaBase.get_setting(self.get_setting_index(event))
        if self.settings.get("sentry_enabled", False):
            sentry_sdk.init(
                dsn=self.settings.get("sentry_dsn"),
                integrations=[AwsLambdaIntegration()],
                traces_sample_rate=float(
                    self.settings.get("sentry_traces_sample_rate", 1.0)
                ),
            )
