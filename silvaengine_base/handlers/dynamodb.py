#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
from typing import Any, Dict, Optional

from silvaengine_dynamodb_base.models import ConfigModel, FunctionModel

from ..handler import Handler


class DynamodbHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "Records" in event
            and len(event["Records"]) > 0
            and event["Records"][0].get("eventSource") == "aws:dynamodb"
        )

    def _extract_table_name(self, arn: str) -> Optional[str]:
        """Extract the DynamoDB table name from its ARN."""
        parts = arn.split("/")

        for i, part in enumerate(parts):
            if ":table" in part:
                return str(parts[i + 1]).strip()
        return None

    def _invoke(
        self,
        endpoint_id: str,
        function_name: str,
        parameters: Dict[str, Any],
    ) -> Any:
        setting, function = self._get_function_and_setting(
            endpoint_id=endpoint_id,
            function_name=function_name,
        )

        if (
            type(function) is not FunctionModel
            or not hasattr(function, "config")
            or not hasattr(function.config, "module_name")
            or not hasattr(function.config, "class_name")
            or not hasattr(function, "function")
        ):
            raise ValueError("Invalid function")

        self._merge_setting_to_default(setting=setting)

        return self._get_proxied_callable(
            module_name=function.config.module_name,
            function_name=function.function,
            class_name=function.config.class_name,
        )(**parameters)

    def handle(self) -> Any:
        try:
            records = self.event.get("Records") or []

            if len(records) < 1:
                return {}

            endpoint_id = self.setting.get(
                "dynamodb_stream_endpoint_id",
                os.getenv("DYNAMODB_STREAM_ENDPOINTID", self._get_endpoint_id()),
            )
            table_name = self._extract_table_name(records[0].get("eventSourceARN"))

            if not table_name:
                return {}

            function_name = self.setting.get("dynamodb_stream_handler", "stream_handle")
            parameters = {
                "records": self.event.get("Records", []),
                "logger": self.logger,
            }

            try:
                dynamodb_stream_config = ConfigModel.find(
                    setting_id=self.setting.get(
                        "dynamodb_stream_config",
                        "dynamodb_stream_config",
                    )
                )
            except Exception:
                dynamodb_stream_config = {}

            if not dynamodb_stream_config.get(table_name):
                return self._invoke(
                    endpoint_id=str(endpoint_id).strip(),
                    function_name=str(function_name).strip(),
                    parameters=parameters,
                )
            else:
                for config in dynamodb_stream_config[table_name]:
                    endpoint_id = config.get("endpoint_id", self._get_endpoint_id())
                    function_name = config.get("funct", "stream_handle")

                    return self._invoke(
                        endpoint_id=str(endpoint_id).strip(),
                        function_name=str(function_name).strip(),
                        parameters=parameters,
                    )

            return {}
        except Exception as e:
            raise e
