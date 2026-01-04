#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import os
import traceback
import urllib.parse
from typing import Any, Dict, Optional, Tuple

import boto3
from silvaengine_utility import Serializer, Utility

from .lambdabase import LambdaBase
from .models import FunctionModel


class Tasks(LambdaBase):
    sns = boto3.client("sns", region_name=os.getenv("REGIONNAME", "us-east-1"))

    def __init__(self, logger: Any) -> None:
        self.logger = logger

    @staticmethod
    def extract_table_name(arn: str) -> Optional[str]:
        """Extract the DynamoDB table name from its ARN."""
        parts = arn.split("/")
        for i, part in enumerate(parts):
            if ":table" in part:
                return parts[i + 1]
        return None

    @classmethod
    def dispatch(
        cls,
        event: Dict[str, Any],
        endpoint_id: str,
        function_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Dispatch a task to the appropriate AWS Lambda function."""
        if not params:
            params = {}

        print(f"Task Dispatch {'=' * 60} {endpoint_id} {function_name}")
        setting, function = cls.get_function(
            endpoint_id=endpoint_id,
            function_name=function_name,
        )
        custom_keys = setting.get("custom_header_keys", [])

        # Parse header keys
        if isinstance(custom_keys, str):
            try:
                custom_keys = Serializer.json_loads(custom_keys)
            except Exception:
                custom_keys = [key for key in custom_keys.split(",")]
        elif not isinstance(custom_keys, list):
            custom_keys = []

        if custom_keys:
            snake_case_keys = {
                Utility.to_snake_case(key.strip()): key
                for key in custom_keys
                if key.strip()
            }
            params.update({k: event[k] for k in snake_case_keys if k in event})

        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": setting,
            "params": params,
        }

        print(f"Task Dispatch {'=' * 60} {Serializer.json_dumps(payload)}")
        print(f"Task Function {'=' * 60} {Serializer.json_dumps(function)}")

        return cls.invoke(
            function_name=function.aws_lambda_arn,
            payload=payload,
            invocation_type=function.config.funct_type,
        )

    def handle(self, event: Dict[str, Any], context: Any) -> None:
        """Main handler function for SQS, S3, and DynamoDB events."""
        try:
            self.logger.info(f"Event Handle {'-' * 60}: {event}")
            self.logger.info(f"Context Handle {'-' * 60}: {context}")
            if event:
                if event.get("Records") and len(event["Records"]) > 0:
                    event_source = event["Records"][0]["eventSource"]

                    if event_source == "aws:sqs":
                        self._handle_sqs_event(event)
                    elif event_source == "aws:s3":
                        self._handle_s3_event(event)
                    elif event_source == "aws:dynamodb":
                        self._handle_dynamodb_event(event)
                    else:
                        raise Exception(f"Unsupported event source: {event_source}")

                elif event.get("bot"):
                    self._handle_bot_event(event)
                else:
                    params = event.get("params", {})

                    if "endpoint_id" not in params and "endpoint_id" in event:
                        params["endpoint_id"] = (
                            str(event.get("endpoint_id")).strip().lower()
                        )

                    return self.dispatch(
                        event,
                        event.get("endpoint_id", ""),
                        event.get("funct", ""),
                        params=params,
                    )
        except Exception as e:
            self.logger.error(f"Error in event handling: {str(e)}")
            log = traceback.format_exc()
            self.logger.exception(log)
            if os.environ.get("SNSTOPICARN"):
                Tasks.sns.publish(
                    TopicArn=os.environ["SNSTOPICARN"],
                    Subject=context.invoked_function_arn,
                    MessageStructure="json",
                    Message=Serializer.json_dumps({"default": log}),
                )

    def _handle_sqs_event(self, event: Dict[str, Any]) -> None:
        """Handle SQS events."""
        for record in event.get("Records", []):
            endpoint_id = record["messageAttributes"]["endpoint_id"].get("stringValue")
            function_name = record["messageAttributes"]["funct"].get("stringValue")
            params = Serializer.json_loads(record["body"]).get("params", {})
            params.update({"endpoint_id": endpoint_id})

            self.logger.info(
                f"(SQS) Endpoint ID: {endpoint_id}, Function: {function_name}, Params: {Serializer.json_dumps(params)}"
            )
            self.dispatch(
                {
                    k: v.get("stringValue")
                    for k, v in record["messageAttributes"].items()
                },
                endpoint_id,
                function_name,
                params=params,
            )

    def _handle_s3_event(self, event: Dict[str, Any]) -> None:
        """Handle S3 events."""
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote(record["s3"]["object"]["key"])

        pieces = key.split("/")
        params = {
            "bucket": bucket,
            "key": key,
            "id": pieces[-1]
            .replace(".csv", "")
            .replace(".xlsx", "")
            .replace(".pdf", ""),
            **{
                piece.split(":")[0]: piece.split(":")[1]
                for piece in pieces
                if ":" in piece
            },
        }

        endpoint_id, function_name = pieces[0], pieces[1]
        self.logger.info(
            f"(S3) Endpoint ID: {endpoint_id}, Function: {function_name}, Params: {Serializer.json_dumps(params)}"
        )
        self.dispatch(event, endpoint_id, function_name, params=params)

    def _handle_dynamodb_event(self, event: Dict[str, Any]) -> None:
        """Handle DynamoDB events."""
        endpoint_id = os.getenv("DYNAMODBSTREAMENDPOINTID", "")
        function_name = "stream_handle"
        params = {"records": event.get("Records", [])}

        table_name = self.extract_table_name(event["Records"][0]["eventSourceARN"])
        try:
            dynamodb_stream_config = LambdaBase.get_setting("dynamodb_stream_config")
        except Exception:
            dynamodb_stream_config = {}

        if not dynamodb_stream_config.get(table_name):
            self.logger.info(
                f"(DynamoDB) Endpoint ID: {endpoint_id}, Function: {function_name}, Params: {Serializer.json_dumps(params)}"
            )
            self.dispatch(event, endpoint_id, function_name, params=params)
        else:
            for config in dynamodb_stream_config[table_name]:
                self.logger.info(
                    f"(DynamoDB) Endpoint ID: {config['endpoint_id']}, Function: {config['funct']}, Params: {Serializer.json_dumps(params)}"
                )
                self.dispatch(
                    event, config["endpoint_id"], config["funct"], params=params
                )

    def _handle_bot_event(self, event: Dict[str, Any]) -> None:
        """Handle bot events."""
        endpoint_id = event["bot"]["id"]
        function_name = f"{event['bot']['name'].lower()}_lex_dispatch"
        params = event

        self.logger.info(
            f"(Lex Bot) Endpoint ID: {endpoint_id}, Function: {function_name}, Params: {Serializer.json_dumps(params)}"
        )
        self.dispatch(event, endpoint_id, function_name, params=params)
