#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import random
import string
import traceback
from datetime import datetime

import jsonpickle
import sentry_sdk
import yaml
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

from silvaengine_base.lambdabase import FunctionError, LambdaBase
from silvaengine_utility import Authorizer as ApiGatewayAuthorizer
from silvaengine_utility import Utility

__author__ = "bibow"


class Resources(LambdaBase):
    settings = {}

    def __init__(self, logger):
        self.logger = logger

    def handle(self, event, context):
        try:
            # Check if the event is from a WebSocket connection
            request_context = event.get("requestContext", {})
            connection_id = request_context.get("connectionId")
            route_key = request_context.get("routeKey")

            if connection_id and route_key:
                self.logger.info(f"WebSocket event received: {event}")

                # Add authorization for WebSocket event
                if not self._authorize_websocket(event, context):
                    return {"statusCode": 403, "body": "Unauthorized"}

                return self._handle_websocket_event(event, connection_id, route_key)

            # If it's not a WebSocket event, handle it as a regular API request
            return self._handle_http_request(event, context)
        except Exception as e:
            return self._handle_exception(e, event)

    def _authorize_websocket(self, event, context):
        """
        Perform authorization for WebSocket events.
        This can be done by checking tokens or permissions during WebSocket events.
        """
        try:
            # Extract authorization token (for example, from headers or query string)
            # auth_token = event.get("headers", {}).get("Authorization") or event.get(
            #     "queryStringParameters", {}
            # ).get("authToken")

            # You can extend this to validate the token with a custom logic or an external service
            # if not auth_token:
            #     self.logger.warning(
            #         "Missing Authorization token for WebSocket connection."
            #     )
            #     return False

            ### Perform the authorization check (replace with your logic)
            is_authorized = True

            if is_authorized:
                self.logger.info("WebSocket authorization successful.")
                return True
            else:
                self.logger.warning("WebSocket authorization failed.")
                return False

        except Exception as e:
            self.logger.error(f"Error during WebSocket authorization: {str(e)}")
            return False

    def _handle_websocket_event(self, event, connection_id, route_key):
        """
        Handle WebSocket connection events including connection, disconnection, and streaming.
        """
        if route_key == "$connect":
            # Handle WebSocket connection
            self.logger.info(f"WebSocket connected: {connection_id}")
            return {"statusCode": 200, "body": "Connection successful"}

        elif route_key == "$disconnect":
            # Handle WebSocket disconnection
            self.logger.info(f"WebSocket disconnected: {connection_id}")
            return {"statusCode": 200, "body": "Disconnection successful"}

        elif route_key == "stream":
            # Handle WebSocket streaming logic
            return self._handle_websocket_stream(event, connection_id)

        # For unsupported WebSocket routes, return a 400 Bad Request
        self.logger.warning(f"Invalid WebSocket route: {route_key}")
        return {"statusCode": 400, "body": "Invalid WebSocket route"}

    def _handle_websocket_stream(self, event, connection_id):
        """
        Process the 'stream' route for WebSocket events, managing the payload and dispatching tasks.
        """
        try:
            est = int(datetime.now().timestamp() * 1000)
            # Parse the incoming WebSocket message
            body = Utility.json_loads(event.get("body", "{}"))
            self.logger.info(f"WebSocket stream received: {body}")

            # Extract required parameters from the message
            endpoint_id = body.get("endpointId")
            funct = body.get("funct")
            params = Utility.json_loads(body.get("payload", "{}"))
            params["endpoint_id"] = endpoint_id

            # Validate required parameters
            if not endpoint_id or not funct:
                self.logger.error(
                    "Missing 'endpointId' or 'funct' in the stream payload"
                )
                return {
                    "statusCode": 400,
                    "body": "Missing required parameters: endpointId or funct",
                }

            # Dispatch the task based on the extracted parameters
            est = self._runtime_debug(endpoint_id, est, f"{funct}:update event(0)")

            # Process function call
            request_context = event.get("requestContext", {})
            api_key = request_context.get("identity", {}).get("apiKey")
            method = self._get_http_method(event)
            setting, function = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )
            return self._invoke_function(
                event, function, funct, params, setting, est, endpoint_id
            )

        except Exception as e:
            self.logger.error(f"Error processing WebSocket stream: {str(e)}")
            return {"statusCode": 500, "body": "Internal Server Error"}

    def _handle_http_request(self, event, context):
        """
        Process regular HTTP API requests when the event is not related to WebSocket.
        """
        api_key, endpoint_id, funct, params = self._extract_event_data(event)
        est = self._initialize_settings(event, endpoint_id, funct)

        # Cognito hooks
        if self._is_cognito_trigger(event):
            return self._handle_cognito_trigger(event, context)

        # Handle API request
        request_context = event.get("requestContext", {})
        method = self._get_http_method(event)
        setting, function = LambdaBase.get_function(
            endpoint_id, funct, api_key=api_key, method=method
        )

        est = self._runtime_debug(endpoint_id, est, f"{funct}:get_function(3)")
        self._validate_function_area(params, function)
        event = self._prepare_event(event, request_context, function, endpoint_id)

        est = self._runtime_debug(endpoint_id, est, f"{funct}:update event(4)")

        # Authorization & Permissions
        if str(event.get("type")).strip().lower() == "request":
            # Authorization
            return self._dynamic_authorization(event, context, "authorize")
        elif event.get("body"):
            # Verify Permissions
            self._dynamic_authorization(event, context, "verify_permission")

        # Process function call
        return self._invoke_function(
            event, function, funct, params, setting, est, endpoint_id
        )

    def _initialize_settings(self, event, endpoint_id, funct):
        """Initialize settings and log start time."""
        est = int(datetime.now().timestamp() * 1000)
        if not self.settings:
            self.init(event)
            est = self._runtime_debug(endpoint_id, est, f"{funct}:init(1)")
        return est

    def _extract_event_data(self, event):
        """Extract and organize event-related data."""
        headers = event.get("headers", {})
        request_context = event.get("requestContext", {})
        path_parameters = event.get("pathParameters", {})

        # Extract necessary fields
        api_key = request_context.get("identity", {}).get("apiKey")
        area = path_parameters.get("area")
        endpoint_id = path_parameters.get("endpoint_id")
        proxy = path_parameters.get("proxy", "")
        query_params = event.get("queryStringParameters", {}) or {}

        # Extract function and optional path from proxy
        funct, _, path = proxy.partition("/")
        if path:
            query_params["path"] = path

        # Merge endpoint_id and area into query parameters
        params = {**query_params, "endpoint_id": endpoint_id, "area": area}

        # Update function name based on headers if unified call index is present
        proxy_index = str(self.settings.get("api_unified_call_index", "")).strip()
        funct = headers.get(proxy_index, funct).strip()

        return api_key, endpoint_id, funct, params

    def _runtime_debug(self, endpoint_id, start_time, mark):
        """Log the execution time for debugging."""
        duration = int(datetime.now().timestamp() * 1000) - start_time

        # Check if endpoint_id is not None before calling strip()
        if not endpoint_id:
            print(f"Warning: `endpoint_id` is missing when executing `{mark}`.")

        if endpoint_id and endpoint_id.strip().lower() == "ss3" and duration > 0:
            print(f"--------- It took {duration} ms to execute request `{mark}`.")

        return int(datetime.now().timestamp() * 1000)

    def _is_cognito_trigger(self, event):
        """Check if the event is a Cognito trigger."""
        return event.get("triggerSource") and event.get("userPoolId")

    def _handle_cognito_trigger(self, event, context):
        """Handle Cognito triggers."""
        return Utility.import_dynamically(
            module_name=self.settings.get(
                "cognito_hooks_module_name", "event_triggers"
            ),
            function_name=self.settings.get(
                "cognito_hooks_function_name", "pre_token_generate"
            ),
            class_name=self.settings.get("cognito_hooks_class_name", "Cognito"),
            constructor_parameters={"logger": self.logger, **self.settings},
        )(event, context)

    def _get_http_method(self, event):
        """Get the HTTP method from the event."""
        return event.get("requestContext", {}).get(
            "httpMethod", event.get("httpMethod", "POST")
        )

    def _validate_function_area(self, params, function):
        """Validate if the area matches the function configuration."""
        area = params.get("area")
        assert (
            area == function.area
        ), f"Area ({area}) does not match the function ({function.area})."

    def _prepare_event(self, event, request_context, function, endpoint_id):
        """Prepare the event data for function invocation."""
        # Use the extracted `endpoint_id` instead of accessing it directly from event
        request_context.update(
            {"channel": endpoint_id, "headers": event.get("headers", {})}
        )
        event.update(
            {
                "fnConfigurations": Utility.json_loads(Utility.json_dumps(function)),
                "requestContext": request_context,
            }
        )
        return event

    def _dynamic_authorization(self, event, context, action):
        """Dynamically handle authorization and permission checks."""

        # Import the correct function dynamically
        fn = Utility.import_dynamically(
            module_name="silvaengine_authorizer",
            function_name=action,
            class_name="Authorizer",
            constructor_parameters={"logger": self.logger},
        )

        # Check if the function is callable
        if callable(fn):
            # Handle 'authorize' action
            if action == "authorize":
                return fn(
                    event, context
                )  # Return the result of the 'authorize' function

            # Handle 'verify_permission' action
            elif action == "verify_permission":
                result = fn(event, context)  # Call 'verify_permission'
                if result:
                    event.update(result)  # Update the event with the result

    def _is_request_event(self, event):
        """Check if the event is of type 'request'."""
        return event.get("type", "").strip().lower() == "request"

    def _invoke_function(
        self, event, function, funct, params, setting, est, endpoint_id
    ):
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
        est = self._runtime_debug(endpoint_id, est, f"{funct}:build payload(7)")

        if function.config.funct_type.strip().lower() == "event":
            LambdaBase.invoke(function.aws_lambda_arn, payload, invocation_type="Event")
            return self._generate_response(200, "")

        result = LambdaBase.invoke(
            function.aws_lambda_arn,
            payload,
            invocation_type=function.config.funct_type.strip(),
        )
        return self._process_response(result)

    def _generate_response(self, status_code, body):
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

    def _process_response(self, result):
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

    def _handle_exception(self, exception, event):
        """Handle and log exceptions."""
        # Log the error with a stack trace
        log = traceback.format_exc()
        self.logger.exception(log)

        # Set default error message and status code
        message = exception.args[0] if exception.args else log
        status_code = (
            exception.args[1]
            if len(exception.args) > 1 and isinstance(exception.args[1], int)
            else 500
        )

        # Handle API Gateway authorizer failures
        if self._is_request_event(event):
            return self._handle_authorizer_failure(event, message)

        # Capture exception in Sentry if enabled and it's a server error
        if str(status_code).startswith("5") and self.settings.get(
            "sentry_enabled", False
        ):
            sentry_sdk.capture_exception(exception)

        # Return a standardized error response
        return self._generate_error_response(status_code, message)

    def _handle_authorizer_failure(self, event, message):
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

    def _generate_error_response(self, status_code, message):
        """Generate a standardized error response."""
        return {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": message}),
        }

    @staticmethod
    def _is_json(content):
        """Check if the content is valid JSON."""
        try:
            json.loads(content)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_yaml(content):
        """Check if the content is valid YAML."""
        try:
            yaml.load(content, Loader=yaml.SafeLoader)
            return True
        except yaml.YAMLError:
            return False

    def get_setting_index(self, event):
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

    # Initialize settings
    def init(self, event):
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
