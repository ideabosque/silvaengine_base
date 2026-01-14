#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import traceback
from typing import Any, Dict, Optional

import pendulum
from silvaengine_constants import AuthorizationAction, HttpStatus, SwitchStatus
from silvaengine_dynamodb_base.models import FunctionModel, WSSConnectionModel
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
        return (
            str(self.event["requestContext"].get("connectionId")).strip().lower() or ""
        )

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
            pass
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
            Debugger.info(
                variable=e,
                stage="WEBSOCKET TEST(handle)",
                delimiter="#",
                logger=self.logger,
            )
            print(traceback.format_exc())
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
                    Debugger.info(
                        variable=e,
                        stage="WEBSOCKET TEST(_dispatch)",
                        delimiter="#",
                        logger=self.logger,
                    )
                    return self._generate_response(
                        status_code=HttpStatus.OK.value,
                        body={"data": str(e)},
                        as_websocket_format=True,
                    )

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

                    WSSConnectionModel.remove(
                        endpoint_id=endpoint_id,
                        email=str(self._get_authorized_user().get("email", "")).strip(),
                    )
            except Exception as e:
                Debugger.info(
                    variable=e,
                    stage="WEBSOCKET TEST(save connection to database)",
                    delimiter="#",
                    logger=self.logger,
                )
                pass

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Connection successful"},
                as_websocket_format=True,
            )

        elif route_key == "$disconnect":
            try:
                wss_connection = self._get_current_connection(
                    endpoint_id=endpoint_id,
                    connection_id=connection_id,
                )

                if wss_connection:
                    wss_connection.delete()
                    # wss_connection.status = SwitchStatus.INACTIVE.name
                    # wss_connection.updated_at = pendulum.now("UTC")
                    # wss_connection.save()
            except Exception as e:
                Debugger.info(
                    variable=e,
                    stage="WEBSOCKET DEBUG(disconnect)",
                    delimiter="#",
                    logger=self.logger,
                    setting=self.setting,
                )
                pass

            return self._generate_response(
                status_code=HttpStatus.OK.value,
                body={"data": "Disconnection successful"},
                as_websocket_format=True,
            )
        elif route_key == "stream":
            return self._message()

        Debugger.info(
            variable="Invalid websocket route",
            stage="WEBSOCKET TEST",
            delimiter="#",
            logger=self.logger,
        )
        return self._generate_response(
            status_code=HttpStatus.OK.value,
            body={"data": "Invalid websocket route"},
            as_websocket_format=True,
        )

    def _message(self) -> Any:
        """
        Process the 'stream' route for WebSocket events, managing the payload and dispatching tasks.
        """
        try:
            connection_id = self._get_connection_id()

            if not connection_id:
                Debugger.info(
                    variable="Invalid websocket connection",
                    stage="WEBSOCKET TEST",
                    delimiter="#",
                    logger=self.logger,
                )
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    body={"data": "Invalid websocket connection id"},
                    as_websocket_format=True,
                )

            endpoint_id = self._get_endpoint_id()

            if not endpoint_id:
                Debugger.info(
                    variable="Invalid websocket connection endpoint id",
                    stage="WEBSOCKET TEST",
                    delimiter="#",
                    logger=self.logger,
                )
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    body={"data": "Invalid websocket connection endpoint id"},
                    as_websocket_format=True,
                )

            wss_connection = self._get_current_connection(
                endpoint_id=endpoint_id,
                connection_id=connection_id,
            )

            if not wss_connection:
                Debugger.info(
                    variable="WebSocket connection not found",
                    stage="WEBSOCKET TEST",
                    delimiter="#",
                    logger=self.logger,
                )
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    body={"data": "WebSocket connection not found"},
                    as_websocket_format=True,
                )

            body = self._parse_event_body()
            function = body.get("funct")

            if not endpoint_id or not function:
                Debugger.info(
                    variable="Missing required parameters: `endpointId` or `funct`",
                    stage="WEBSOCKET TEST",
                    delimiter="#",
                    logger=self.logger,
                )
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    as_websocket_format=True,
                    body={
                        "data": "Missing required parameters: `endpointId` or `funct`"
                    },
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

            url_parameters = wss_connection.url_parameters.as_dict()

            if isinstance(url_parameters, dict):
                parameters.update(
                    metadata=self._extract_additional_parameters(
                        url_parameters,
                    )
                )

            if (
                not isinstance(function, FunctionModel)
                or not hasattr(function, "config")
                or not hasattr(function.config, "module_name")
                or not hasattr(function.config, "class_name")
                or not hasattr(function, "function")
            ):
                Debugger.info(
                    variable="Invalid function",
                    stage="WEBSOCKET TEST",
                    delimiter="#",
                    logger=self.logger,
                )
                return self._generate_response(
                    status_code=HttpStatus.OK.value,
                    as_websocket_format=True,
                    body={"data": "Invalid function"},
                )

            Debugger.info(
                variable=parameters,
                stage="WEBSOCKET TEST",
                delimiter="#",
                logger=self.logger,
            )

            r = self._get_proxied_callable(
                module_name=function.config.module_name,
                class_name=function.config.class_name,
                function_name=function.function,
            )(**parameters)

            Debugger.info(
                variable=parameters,
                stage="WEBSOCKET RESPONSE",
                delimiter="+",
                logger=self.logger,
            )

            return r
        except Exception as e:
            raise e
