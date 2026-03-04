#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

from typing import Any, Dict, List

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
        message_id = record.get("messageId", "unknown")

        try:
            endpoint_id = (
                self._get_message_attribute(record=record, attribute="endpoint_id").get("stringValue")
                or self._get_endpoint_id()
            )
            function_name = self._get_message_attribute(
                record=record, attribute="funct"
            ).get("stringValue")

            if not function_name:
                self.logger.warning(f"Missing function_name for message {message_id}")
                return {"message_id": message_id, "status": "skipped", "reason": "missing_function_name"}

            parameters = {
                **self._get_event_body(record=record).get("params", {}),
                "endpoint_id": endpoint_id,
                "logger": self.logger,
            }

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

            return {"message_id": message_id, "status": "success", "result": result}

        except Exception as e:
            self.logger.error(f"Failed to process message {message_id}: {e}")
            return {"message_id": message_id, "status": "failed", "error": str(e)}

    def handle(self) -> Any:
        records = self.event.get("Records", [])

        if not records:
            self.logger.warning("No records found in SQS event")
            return {"processed": 0, "results": []}

        self.logger.info(f"Processing {len(records)} SQS messages")

        results: List[Dict[str, Any]] = []

        for index, record in enumerate(records):
            self.logger.debug(f"Processing record {index + 1}/{len(records)}")
            result = self._process_single_record(record)
            results.append(result)

        success_count = sum(1 for r in results if r.get("status") == "success")
        failed_count = sum(1 for r in results if r.get("status") == "failed")

        self.logger.info(
            f"SQS processing complete: {success_count} succeeded, {failed_count} failed"
        )

        return {
            "processed": len(results),
            "succeeded": success_count,
            "failed": failed_count,
            "results": results,
        }
