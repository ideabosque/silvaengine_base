#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

import pendulum
from silvaengine_dynamodb_base.models import FunctionModel, WSSConnectionModel

from silvaengine_constants import AuthorizationAction, HttpStatus, SwitchStatus
from silvaengine_utility import Serializer

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
        return (
            str(self.event["requestContext"].get("connectionId")).strip().lower() or ""
        )

    def _get_route_key(self):
        return str(self.event["requestContext"].get("routeKey")).strip().lower() or ""

    def _parse_event_body_parameters(self) -> Dict[str, Any]:
        try:
            body = self._parse_event_body()

            return (
                Serializer.json_loads(body.get("payload"))
                if body.get("payload") is not None
                else {}
            )
        except Exception:
            pass
        return {}

    def handle(self) -> Any:
        connection_id = self._get_connection_id()
        route_key = self._get_route_key()

        if connection_id and route_key:
            return self._dispatch(connection_id, route_key)

        return {}

    def _dispatch(self, connection_id: str, route_key: str) -> Any:
        """
        Handle WebSocket connection events including connection, disconnection, and streaming.
        """
        if route_key == "$connect":
            if self._is_authorization_event():
                try:
                    return self._invoke_authorization(
                        action=AuthorizationAction.AUTHORIZE
                    )
                except Exception as e:
                    raise e

            url_parameters = self._get_query_string_parameters()
            endpoint_id = self._get_endpoint_id()
            area = self._get_api_area()
            api_key = self._get_api_key()

            url_parameters.update(connection_id=connection_id)

            if not api_key and not endpoint_id:
                WSSConnectionModel.store(
                    endpoint_id=endpoint_id,
                    connection_id=connection_id,
                    url_parameters=url_parameters,
                    area=area,
                    api_key=api_key,
                    data=self._get_authorized_user(),
                )
                WSSConnectionModel.remove(
                    endpoint_id=endpoint_id,
                    email=str(self._get_authorized_user().get("email", "")).strip(),
                )

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Connection successful"},
            )

        elif route_key == "$disconnect":
            results = WSSConnectionModel.find(connection_id)
            wss_onnection = [result for result in results][0]

            if wss_onnection:
                wss_onnection.status = SwitchStatus.INACTIVE.value
                wss_onnection.updated_at = pendulum.now("UTC")
                wss_onnection.save()

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Disconnection successful"},
            )
        elif route_key == "stream":
            return self._message()

        return self._generate_response(
            status_code=HttpStatus.BAD_REQUEST.value,
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
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Invalid webSocket connection"},
                )

            results = WSSConnectionModel.find(connection_id)

            if not results:
                return self._generate_response(
                    status_code=HttpStatus.NOT_FOUND.value,
                    body={"data": "Not found any websocket connections"},
                )

            wss_onnection = [result for result in results][0]

            if not wss_onnection:
                return self._generate_response(
                    status_code=HttpStatus.NOT_FOUND.value,
                    body={"data": "WebSocket connection not found"},
                )

            endpoint_id = wss_onnection.endpoint_id

            if not endpoint_id:
                endpoint_id = self._get_endpoint_id()

            body = self._parse_event_body()
            function = body.get("funct")

            if not endpoint_id or not function:
                return self._generate_response(
                    status_code=HttpStatus.BAD_REQUEST.value,
                    body={"data": "Missing required parameters: endpointId or funct"},
                )

            parameters = {
                **self._parse_event_body_parameters(),
                "endpoint_id": endpoint_id,
                "connection_id": connection_id,
            }
            api_key = self._get_api_key()
            method = self._get_request_method()
            setting, function = self._get_function_and_setting(
                endpoint_id=endpoint_id,
                function_name=function,
                api_key=api_key,
                method=method,
            )

            self._merge_setting_to_default(setting=setting)

            url_parameters = wss_onnection.url_parameters.as_dict()

            if type(url_parameters) is dict:
                parameters.update(
                    self._extract_additional_parameters(
                        url_parameters,
                    )
                )

            if (
                type(function) is not FunctionModel
                or not hasattr(function, "config")
                or not hasattr(function.config, "module_name")
                or not hasattr(function.config, "class_name")
                or not hasattr(function, "function")
            ):
                raise ValueError("Invalid function")

            return self._get_proxied_callable(
                module_name=function.config.module_name,
                class_name=function.config.class_name,
                function_name=function.function,
            )
        except Exception as e:
            raise e
