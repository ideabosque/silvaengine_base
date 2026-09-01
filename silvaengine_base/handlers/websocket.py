#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
from typing import Any, Dict, Optional

import boto3
import pendulum
from botocore.exceptions import ClientError
from silvaengine_dynamodb_base.models import (
    DoesNotExist,
    FunctionModel,
    WSSConnectionModel,
)

from silvaengine_constants import AuthorizationAction, HttpStatus, InvocationType
from silvaengine_utility import Debugger

from ..handler import Handler


class WebSocketHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        # Internal asynchronous tasks (welcome dispatch, connection cleanup)
        # are self-invoked Lambda events carrying a `_internal_task` marker.
        # They have no requestContext, so they are matched here explicitly.
        if isinstance(event, dict) and event.get("_internal_task"):
            return True

        # A WebSocket message that reached the Lambda WITHOUT its requestContext
        # wrapper (e.g. an `ask_model` route integration that forwards only the
        # body instead of the API Gateway WebSocket proxy event). We match it
        # here so we can emit an actionable diagnostic instead of the opaque
        # "Unrecognized event" from DefaultHandler. No other handler matches
        # this shape, so there is no risk of shadowing.
        if (
            isinstance(event, dict)
            and not event.get("requestContext")
            and not event.get("__type")
            and isinstance(event.get("action"), str)
            and str(event.get("action")).strip()
            and isinstance(event.get("arguments"), dict)
        ):
            return True

        return (
            "requestContext" in event
            and "connectionId" in event["requestContext"]
            and "routeKey" in event["requestContext"]
        )

    def _get_connection_id(self):
        return str(self.event["requestContext"].get("connectionId")).strip() or ""

    def _get_route_key(self):
        return str(self.event["requestContext"].get("routeKey")).strip().lower() or ""

    def _get_current_connection(
        self,
        endpoint_id: str,
        connection_id: str,
    ) -> Optional[WSSConnectionModel]:
        return WSSConnectionModel.get(
            hash_key=endpoint_id,
            range_key=connection_id,
        )

    def _parse_event_body_parameters(self) -> Dict[str, Any]:
        try:
            body = self._parse_event_body()

            return body.get("arguments") if body.get("arguments") is not None else {}
        except Exception:
            return {}

    def _get_websocket_callback_url(self) -> str:
        """
        Build the callback endpoint URL for the WebSocket API Gateway Management API.

        Resolution order:
        1. If `requestContext.domainName` is the raw execute-api endpoint
           (`*.execute-api.<region>.amazonaws.com`), use it directly with the stage.
        2. Otherwise (custom domain mapping or missing domainName), prefer the
           explicit `WEBSOCKET_CALLBACK_URL` env override so that
           apigatewaymanagementapi routes to the correct API/stage. This is the
           critical fallback for the GoneException root cause where a custom
           domain name makes the connection unresolvable via the mapped host.
        3. As a last resort, fall back to whatever domainName is present.
        """
        request_context = self.event.get("requestContext") or {}
        domain_name = str(request_context.get("domainName") or "").strip()
        stage = (
            str(request_context.get("stage") or "").strip()
            or self._get_api_stage()
        )

        env_callback_url = str(os.getenv("WEBSOCKET_CALLBACK_URL", "")).strip()

        if domain_name and ".execute-api." in domain_name:
            return f"https://{domain_name}/{stage}"

        if env_callback_url:
            base = env_callback_url.rstrip("/")
            return f"{base}/{stage}" if stage else base

        if domain_name:
            return f"https://{domain_name}/{stage}"

        return ""

    def _resolve_aws_region(self, domain_name: str = "") -> str:
        """
        Resolve the AWS region used to sign apigatewaymanagementapi requests.

        Order: `REGION_NAME`/`REGIONNAME` env var > parsed from the execute-api
        domain (`<apiid>.execute-api.<region>.amazonaws.com`) > `us-east-1`.
        Region mismatch is a known GoneException cause when the WebSocket API
        lives in a different region than the signing region.
        """
        env_region = str(
            os.getenv("REGION_NAME", os.getenv("REGIONNAME", "")) or ""
        ).strip()
        if env_region:
            return env_region.lower()

        if domain_name and ".execute-api." in domain_name:
            # e.g. abc123.execute-api.us-east-1.amazonaws.com
            parts = domain_name.split(".")
            # parts[2] is the region segment
            if len(parts) > 3 and parts[1] == "execute-api":
                return parts[2].lower()

        return "us-east-1"

    def _post_to_connection(
        self,
        connection_id: str,
        data: Any,
        endpoint_url: Optional[str] = None,
        endpoint_id: Optional[str] = None,
    ) -> bool:
        """
        Send a message to an existing WebSocket connection via the API Gateway
        Management API. Returns True on success, False on failure.

        :param connection_id: The WebSocket connection id to send data to.
        :param data: The payload to send; non-str values are JSON-serialized.
        :param endpoint_url: The callback endpoint URL; if omitted, derived from
                             the current event's requestContext.
        :param endpoint_id: The endpoint id, used to clean up the DynamoDB record
                            when the connection is gone (GoneException).
        """
        if not connection_id:
            return False

        request_context = self.event.get("requestContext") or {}
        domain_name = str(request_context.get("domainName") or "").strip()
        stage = str(request_context.get("stage") or "").strip()
        request_id = str(request_context.get("requestId") or "")

        callback_url = endpoint_url or self._get_websocket_callback_url()
        region = self._resolve_aws_region(domain_name=domain_name)

        if not callback_url:
            Debugger.info(
                variable={
                    "message": "Missing WebSocket callback URL (domainName/stage).",
                    "connection_id": connection_id,
                    "endpoint_id": endpoint_id,
                    "env_WEBSOCKET_CALLBACK_URL": bool(
                        os.getenv("WEBSOCKET_CALLBACK_URL")
                    ),
                },
                stage="WEBSOCKET POST TO CONNECTION",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )
            return False

        payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)

        try:
            apigw_client = boto3.client(
                "apigatewaymanagementapi",
                endpoint_url=callback_url,
                region_name=region,
            )
            apigw_client.post_to_connection(
                ConnectionId=connection_id,
                Data=payload,
            )
            return True
        except ClientError as e:
            response = getattr(e, "response", {}) or {}
            error_code = str(
                (response.get("Error") or {}).get("Code") or ""
            ).strip()
            http_status = (
                (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            )

            Debugger.info(
                variable={
                    "error": str(e),
                    "error_code": error_code,
                    "http_status": http_status,
                    "connection_id": connection_id,
                    "endpoint_id": endpoint_id,
                    "callback_url": callback_url,
                    "domain_name": domain_name,
                    "stage": stage,
                    "region": region,
                    "request_id": request_id,
                },
                stage="WEBSOCKET POST TO CONNECTION",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )

            # GoneException (HTTP 410): the connection no longer exists on the
            # API Gateway side. Drop the stale DynamoDB record so subsequent
            # lookups/invocations do not target a dead connection. Never rethrow.
            if error_code == "GoneException" and endpoint_id:
                try:
                    wss_connection = self._get_current_connection(
                        endpoint_id=endpoint_id,
                        connection_id=connection_id,
                    )

                    if wss_connection:
                        wss_connection.delete()
                except Exception as cleanup_error:
                    if not isinstance(cleanup_error, DoesNotExist):
                        Debugger.info(
                            variable=cleanup_error,
                            stage="WEBSOCKET GONE CLEANUP",
                            delimiter="#",
                            setting=self.setting,
                            logger=self.logger,
                        )
            return False
        except Exception as e:
            Debugger.info(
                variable=e,
                stage="WEBSOCKET POST TO CONNECTION",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )
            return False

    def handle(self) -> Any:
        # Internal asynchronous tasks (welcome dispatch / connection cleanup)
        # are self-invoked Lambda events. They carry `_internal_task` and have no
        # requestContext, so route them before the normal WebSocket dispatch.
        internal_task = (self.event or {}).get("_internal_task")

        if internal_task:
            return self._handle_internal_task(str(internal_task).strip().lower())

        # A WebSocket message body that arrived WITHOUT its requestContext
        # wrapper. A real API Gateway WebSocket event always carries
        # `requestContext` (connectionId / routeKey / domainName / stage); a
        # bare `{action, arguments}` payload means the route integration is
        # forwarding only the body instead of the proxy event. Without
        # requestContext there is no connectionId, so the message cannot be
        # routed or answered. Surface a clear, actionable diagnostic instead
        # of the generic "Unrecognized event".
        event = self.event or {}

        if not event.get("requestContext") and event.get("action"):
            action = str(event.get("action")).strip()
            Debugger.info(
                variable={
                    "message": (
                        "WebSocket message received without requestContext; "
                        "the route integration is not delivering the API Gateway "
                        "WebSocket proxy event."
                    ),
                    "action": action,
                    "event_keys": sorted(event.keys()),
                },
                stage="WEBSOCKET BODY WITHOUT REQUEST_CONTEXT",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )
            return self._generate_response(
                status_code=HttpStatus.BAD_REQUEST.value,
                body={
                    "data": (
                        "WebSocket message received without requestContext. The "
                        "API Gateway route integration must deliver the WebSocket "
                        "proxy event (requestContext.connectionId/routeKey), not the "
                        "raw body. Verify the route selection expression "
                        "($request.body.action) and the route's Lambda integration."
                    ),
                    "action": action,
                },
            )

        try:
            connection_id = self._get_connection_id()
            route_key = self._get_route_key()

            if not connection_id and not route_key:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Missing required `connection_id` or `route_key`"},
                )

            return self._dispatch(connection_id=connection_id, route_key=route_key)
        except Exception as e:
            if isinstance(e, DoesNotExist):
                e = "The connection has been terminated, please establish a new connection."

            Debugger.info(
                variable=e,
                stage="WEBSOCKET TEST(handle)",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )
            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": str(e)},
            )

    def _dispatch(self, connection_id: str, route_key: str) -> Any:
        """
        Handle WebSocket connection events including connection, disconnection, and streaming.
        """
        endpoint_id = self._get_endpoint_id()

        if route_key == "$connect":
            if self._is_authorization_event():
                try:
                    return self._invoke_authorization(
                        action=AuthorizationAction.AUTHORIZE
                    )
                except Exception as e:
                    raise e

            try:
                url_parameters = self._get_query_string_parameters()
                area = self._get_api_area()
                api_key = self._get_api_key()

                url_parameters.update(connection_id=connection_id)

                if api_key and endpoint_id:
                    WSSConnectionModel.store(
                        endpoint_id=endpoint_id,
                        connection_id=connection_id,
                        url_parameters=url_parameters,
                        area=area,
                        api_key=api_key,
                        data=self._get_authorized_user(),
                    )

                    # Dispatch the welcome message and stale-connection cleanup
                    # asynchronously via a self-invoked Lambda (EVENT type). The
                    # WebSocket connection is only addressable through
                    # apigatewaymanagementapi once `$connect` returns 200 to API
                    # Gateway; posting synchronously inside `$connect` races the
                    # handshake and raises GoneException. Moving both the welcome
                    # push and the (potentially slow) cleanup off the hot path
                    # keeps the handshake fast and isolates their failures from the
                    # connection response.
                    callback_url = self._get_websocket_callback_url()

                    self._dispatch_internal_task(
                        task="send_welcome",
                        payload={
                            "connection_id": connection_id,
                            "callback_url": callback_url,
                            "endpoint_id": endpoint_id,
                        },
                    )
                    self._dispatch_internal_task(
                        task="cleanup_connections",
                        payload={
                            "endpoint_id": endpoint_id,
                            "expires_in_minutes": 10,
                        },
                    )
            except Exception as e:
                if not isinstance(e, DoesNotExist):
                    raise e
                pass

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Connection successful"},
            )

        elif route_key == "$disconnect":
            try:
                wss_connection = self._get_current_connection(
                    endpoint_id=endpoint_id,
                    connection_id=connection_id,
                )

                if wss_connection:
                    wss_connection.delete()
            except Exception as e:
                if not isinstance(e, DoesNotExist):
                    raise e
                pass

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Disconnection successful"},
            )
        elif route_key in ["ask_model"]:
            # `ask_model` is a friendly WebSocket route alias. The function
            # registered in se-connections for this endpoint is
            # `async_execute_ask_model` (ai_agent_core_engine.AIAgentCoreEngine),
            # so map the route to that function name for the lookup.
            return self._message(function=route_key)
        elif route_key == "ping":
            # The health_check internal task runs in a self-invoked Lambda event
            # without requestContext, so the callback URL must be resolved here
            # (while the original WebSocket event still carries domainName/stage)
            # and forwarded in the payload, exactly like send_welcome.
            self._dispatch_internal_task(
                task="health_check",
                payload={
                    "endpoint_id": endpoint_id,
                    "connection_id": connection_id,
                    "callback_url": self._get_websocket_callback_url(),
                },
            )
            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "WebSocket connection health check passed"},
            )

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "Invalid websocket route"},
        )

    def _dispatch_internal_task(
        self,
        task: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Asynchronously self-invoke this Lambda to run an internal task
        (`send_welcome` / `cleanup_connections`). Failures are logged only and
        never propagated, so the caller (e.g. `$connect`) response is unaffected.
        """
        try:
            function_name = str(
                getattr(self.context, "function_name", "") or ""
            ).strip()

            if not function_name:
                Debugger.info(
                    variable="Missing function_name for internal task dispatch.",
                    stage="WEBSOCKET DISPATCH INTERNAL TASK",
                    delimiter="#",
                    setting=self.setting,
                    logger=self.logger,
                )
                return

            task_payload = dict(payload)
            task_payload["_internal_task"] = task

            self.invoke_aws_lambda_function(
                function_name=function_name,
                payload=task_payload,
                invocation_type=InvocationType.EVENT,
            )
        except Exception as e:
            Debugger.info(
                variable=e,
                stage="WEBSOCKET DISPATCH INTERNAL TASK",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )

    def _handle_internal_task(self, task: str) -> Any:
        """
        Entry point for self-invoked asynchronous internal tasks. These run in a
        separate Lambda invocation, isolated from the originating `$connect`
        handshake, so their outcome never affects the connection response.
        """
        try:
            if task == "send_welcome":
                return self._internal_send_welcome()
            elif task == "cleanup_connections":
                return self._internal_cleanup_connections()
            elif task == "health_check":
                return self._internal_health_check()

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": f"Unknown internal task: {task}"},
            )
        except Exception as e:
            Debugger.info(
                variable=e,
                stage="WEBSOCKET INTERNAL TASK",
                delimiter="#",
                setting=self.setting,
                logger=self.logger,
            )
            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": str(e)},
            )

    def _internal_send_welcome(self) -> Any:
        """
        Asynchronous welcome-message dispatch. Runs after `$connect` has
        returned, so the connection is fully addressable via
        apigatewaymanagementapi. GoneException (connection already closed by
        the client) is handled and cleans up the stale DynamoDB record.
        """
        params = self.event or {}
        connection_id = str(params.get("connection_id") or "").strip()
        callback_url = str(params.get("callback_url") or "").strip()
        endpoint_id = str(params.get("endpoint_id") or "").strip()

        data = {
            "type": "connection_ack",
            "connection_id": connection_id,
        }

        self._post_to_connection(
            connection_id=connection_id,
            data=data,
            endpoint_url=callback_url or None,
            endpoint_id=endpoint_id,
        )

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "welcome dispatched"},
        )

    def _internal_cleanup_connections(self) -> Any:
        """
        Asynchronous stale-connection cleanup. Moved off the `$connect` hot
        path so a slow DynamoDB scan/delete does not delay the handshake.
        """
        params = self.event or {}
        endpoint_id = str(params.get("endpoint_id") or "").strip()
        expires_in_minutes = int(params.get("expires_in_minutes") or 10)

        if endpoint_id:
            WSSConnectionModel.cleanup_connections(
                endpoint_id=endpoint_id,
                expires_in_minutes=expires_in_minutes,
            )

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "cleanup done"},
        )

    def _internal_health_check(self) -> Any:
        """
        Asynchronous welcome-message dispatch. Runs after `$connect` has
        returned, so the connection is fully addressable via
        apigatewaymanagementapi. GoneException (connection already closed by
        the client) is handled and cleans up the stale DynamoDB record.
        """
        params = self.event or {}
        connection_id = str(params.get("connection_id") or "").strip()
        callback_url = str(params.get("callback_url") or "").strip()
        endpoint_id = str(params.get("endpoint_id") or "").strip()

        data = {
            "type": "pong",
            "connection_id": connection_id,
            "message": int(pendulum.now().timestamp()),
        }

        self._post_to_connection(
            connection_id=connection_id,
            data=data,
            endpoint_url=callback_url or None,
            endpoint_id=endpoint_id,
        )

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "Health checked"},
        )

    def _message(self, function: str) -> Any:
        """
        Process the specified function for WebSocket events, managing the payload and dispatching tasks.
        """
        try:
            connection_id = self._get_connection_id()

            if not connection_id:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Invalid websocket connection id"},
                )

            api_key, endpoint_id, parameters = self._extract_core_parameters()

            if not endpoint_id:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Invalid websocket connection endpoint id"},
                )

            if not function:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Missing required `funct`"},
                )

            parameters.update(
                endpoint_id=endpoint_id,
                connection_id=connection_id,
                api_key=api_key,
                **self._parse_event_body_parameters(),
            )
            setting, function = self._get_function_and_setting(
                endpoint_id=endpoint_id,
                function_name=function,
                api_key=api_key,
                method=self._get_request_method(),
            )

            self._merge_setting_to_default(setting=setting)

            wss_connection = self._get_current_connection(
                endpoint_id=endpoint_id,
                connection_id=connection_id,
            )

            if not wss_connection:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "WebSocket connection not found"},
                )
            elif hasattr(wss_connection, "updated_at"):
                wss_connection.updated_at = pendulum.now("UTC")
                wss_connection.save()

            metadata = self._get_metadata(endpoint_id=endpoint_id)
            url_parameters = wss_connection.url_parameters.as_dict()

            if isinstance(url_parameters, dict) and len(url_parameters) > 0:
                extra = self._extract_additional_parameters(url_parameters)

                if isinstance(extra, dict) and len(extra) > 0:
                    metadata.update(extra)

            if isinstance(parameters.get("metadata"), dict):
                parameters["metadata"].update(metadata)
            else:
                parameters["metadata"] = metadata

            if (
                not isinstance(function, FunctionModel)
                or not hasattr(function, "config")
                or not hasattr(function.config, "module_name")
                or not hasattr(function.config, "class_name")
                or not hasattr(function, "function")
                or not hasattr(function, "aws_lambda_arn")
            ):
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Invalid function"},
                )

            self._get_proxied_callable(
                module_name=function.config.module_name,
                class_name=function.config.class_name,
                function_name=function.function,
            )(aws_lambda_arn=function.aws_lambda_arn, **parameters)
        except Exception as e:
            raise e

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "Sent message to client successful"},
        )
