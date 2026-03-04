#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import urllib.parse
from typing import Any, Dict, List

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

    def _extract_file_id(self, filename: str) -> str:
        return os.path.splitext(filename)[0]

    def _parse_path_parameters(self, pieces: List[str]) -> Dict[str, str]:
        params = {}
        for piece in pieces:
            if ":" in piece:
                key, value = piece.split(":", 1)
                params[key] = value
        return params

    def _validate_function(self, function: Any) -> FunctionModel:
        if not isinstance(function, FunctionModel):
            raise ValueError("Function must be a FunctionModel instance")

        required_attrs = ["config", "function", "aws_lambda_arn"]
        for attr in required_attrs:
            if not hasattr(function, attr):
                raise ValueError(f"Function missing required attribute: {attr}")

        config_attrs = ["module_name", "class_name"]
        for attr in config_attrs:
            if not hasattr(function.config, attr):
                raise ValueError(f"Function config missing required attribute: {attr}")

        return function

    def _process_single_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        try:
            bucket = str(record.get("s3", {}).get("bucket", {}).get("name", "")).strip()
            object_key = str(
                record.get("s3", {}).get("object", {}).get("key", "")
            ).strip()

            if not bucket or not object_key:
                return {"status": "skipped", "reason": "missing_bucket_or_key"}

            key = urllib.parse.unquote(object_key)
            pieces = key.split("/")

            if len(pieces) < 2:
                return {"status": "skipped", "reason": "invalid_path_format"}

            file_id = self._extract_file_id(pieces[-1])
            path_params = self._parse_path_parameters(pieces)

            parameters = {
                "logger": self.logger,
                "bucket": bucket,
                "key": key,
                "id": file_id,
                **path_params,
            }

            endpoint_id = pieces[0] or self._get_endpoint_id()
            function_name = pieces[1]

            if not function_name:
                return {"status": "skipped", "reason": "missing_function_name"}

            setting, function = self._get_function_and_setting(
                endpoint_id=endpoint_id,
                function_name=str(function_name).strip(),
            )

            self._validate_function(function)
            self._merge_setting_to_default(setting=setting)

            result = self._get_proxied_callable(
                module_name=function.config.module_name,
                function_name=function.function,
                class_name=function.config.class_name,
            )(aws_lambda_arn=function.aws_lambda_arn, **parameters)

            return {"status": "success", "key": key, "result": result}

        except Exception as e:
            self.logger.error(f"Failed to process S3 record: {e}")
            return {"status": "failed", "error": str(e)}

    def handle(self) -> Any:
        records = self.event.get("Records", [])

        if not isinstance(records, list) or len(records) == 0:
            self.logger.warning("No records found in S3 event")
            return {}

        self.logger.info(f"Processing {len(records)} S3 event records")

        results: List[Dict[str, Any]] = []

        for index, record in enumerate(records):
            self.logger.debug(f"Processing S3 record {index + 1}/{len(records)}")
            result = self._process_single_record(record)
            results.append(result)

        success_count = sum(1 for r in results if r.get("status") == "success")
        failed_count = sum(1 for r in results if r.get("status") == "failed")

        self.logger.info(
            f"S3 processing complete: {success_count} succeeded, {failed_count} failed"
        )

        return {
            "processed": len(results),
            "succeeded": success_count,
            "failed": failed_count,
            "results": results,
        }
