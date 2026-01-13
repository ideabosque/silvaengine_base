#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import urllib.parse
from typing import Any, Dict

from silvaengine_dynamodb_base.models import FunctionModel

from ..handler import Handler


class S3Handler(Handler):
    @classmethod
    def is_event_match_handler(cls, event: Dict[str, Any]) -> bool:
        return (
            "Records" in event
            and len(event["Records"]) > 0
            and "s3" in event["Records"][0]
        )

    def handle(self) -> Any:
        try:
            if type(self.event["Records"]) is list and len(self.event["Records"]) > 0:
                record = self.event["Records"][0]
                bucket = str(record.get("s3", {}).get("bucket", {}).get("name")).strip()
                object_key = str(
                    record.get("s3", {}).get("object", {}).get("key")
                ).strip()
                key = urllib.parse.unquote(object_key)
                pieces = key.split("/")
                id = (
                    pieces[-1]
                    .replace(".csv", "")
                    .replace(".xlsx", "")
                    .replace(".pdf", "")
                )
                parameters = {
                    "logger": self.logger,
                    "bucket": bucket,
                    "key": key,
                    "id": id,
                    **{
                        piece.split(":")[0]: piece.split(":")[1]
                        for piece in pieces
                        if ":" in piece
                    },
                }

                endpoint_id, function_name = pieces[0], pieces[1]

                if not endpoint_id:
                    endpoint_id = self._get_endpoint_id()

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
