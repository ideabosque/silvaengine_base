#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict

from silvaengine_dynamodb_base.models import FunctionModel

from silvaengine_utility import Serializer

from ..handler import Handler


class SQSHandler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "Records" in event
            and len(event["Records"]) > 0
            and event["Records"][0].get("eventSource") == "aws:sqs"
        )

    def _get_event_body(self, record: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return Serializer.json_loads(record.get("body", "{}"))
        except Exception:
            pass

        return {}

    def _get_message_attribute(
        self, record: Dict[str, Any], attribute: str
    ) -> Dict[str, Any]:
        if record:
            return record.get("messageAttributes", {}).get(str(attribute).strip(), {})
        return {}

    def handle(self) -> Any:
        try:
            for record in self.event.get("Records", []):
                endpoint_id = (
                    self._get_message_attribute(
                        record=record, attribute="endpoint_id"
                    ).get("stringValue")
                    or self._get_endpoint_id()
                )
                function_name = self._get_message_attribute(
                    record=record, attribute="funct"
                ).get("stringValue")
                parameters = {
                    **self._get_event_body(record=record).get("params", {}),
                    "endpoint_id": endpoint_id,
                    "logger": self.logger,
                }
                setting, function = self._get_function_and_setting(
                    endpoint_id=endpoint_id,
                    function_name=str(function_name).strip(),
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

            return {}
        except Exception as e:
            raise e
