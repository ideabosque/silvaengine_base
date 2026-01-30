#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import traceback
from typing import Any, Dict, Optional

import pendulum
from silvaengine_dynamodb_base.models import (
    DoesNotExist,
    FunctionModel,
    WSSConnectionModel,
)

from silvaengine_constants import AuthorizationAction, HttpStatus, SwitchStatus
from silvaengine_utility import Debugger, Serializer

from ..handler import Handler


class WebSocketHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
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

            return (
                Serializer.json_loads(body.get("payload"))
                if body.get("payload") is not None
                else {}
            )
        except Exception:
            return {}

    def handle(self) -> Any:
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

                    WSSConnectionModel.cleanup_connections(
                        endpoint_id=endpoint_id,
                        expires_in_minutes=10,
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
        elif route_key == "stream":
            return self._message()

        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "Invalid websocket route"},
        )

    def _message(self) -> Any:
        """
        Process the 'stream' route for WebSocket events, managing the payload and dispatching tasks.
        """
        try:
            connection_id = self._get_connection_id()

            if not connection_id:
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    body={"data": "Invalid websocket connection id"},
                )

            api_key, endpoint_id, parameters = self._extract_core_parameters()

            if not endpoint_id:
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    body={"data": "Invalid websocket connection endpoint id"},
                )

            body = self._parse_event_body()
            function = body.get("funct")

            if not function:
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
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
                    status_code=HttpStatus.OK.value,
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
                    status_code=HttpStatus.OK.value,
                    body={"data": "Invalid function"},
                )

            return self._get_proxied_callable(
                module_name=function.config.module_name,
                class_name=function.config.class_name,
                function_name=function.function,
            )(aws_lambda_arn=function.aws_lambda_arn, **parameters)
        except Exception as e:
            raise e
