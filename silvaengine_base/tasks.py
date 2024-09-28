#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import os
import traceback
import urllib.parse
from typing import Any, Dict, Optional

import boto3

from silvaengine_utility import Utility

from .lambdabase import LambdaBase


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
        cls, endpoint_id: str, funct: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Dispatch a task to the appropriate AWS Lambda function."""
        print("-" * 50 + " START " + "-" * 50)
        print(f"Endpoint ID: {endpoint_id}, Function: {funct}")
        setting, function = cls.get_function(endpoint_id, funct)
        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": Utility.json_dumps(setting),
            "params": Utility.json_dumps(params),
        }
        print(
            f"Function ARN: {function.aws_lambda_arn}, Type: {function.config.funct_type}, Payload: {payload}"
        )
        print("-" * 50 + " END " + "-" * 50)

        result = cls.invoke(
            function.aws_lambda_arn, payload, invocation_type=function.config.funct_type
        )
        print(">>>>>>>>>>> TASK EXECUTE RESULT::::", result)
        return result

    def handle(self, event: Dict[str, Any], context: Any) -> None:
        """Main handler function for SQS, S3, and DynamoDB events."""
        try:
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
                self.logger.info(
                    f"Endpoint ID: {event.get('endpoint_id')}, Function: {event.get('funct')}, Params: {Utility.json_dumps(event.get('params'))}"
                )
                return self.dispatch(
                    event.get("endpoint_id"),
                    event.get("funct"),
                    params=dict(
                        {"endpoint_id": event.get("endpoint_id")}, **event.get("params")
                    ),
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
                    Message=Utility.json_dumps({"default": log}),
                )

    def _handle_sqs_event(self, event: Dict[str, Any]) -> None:
        """Handle SQS events."""
        for record in event.get("Records", []):
            endpoint_id = record["messageAttributes"]["endpoint_id"].get("stringValue")
            funct = record["messageAttributes"]["funct"].get("stringValue")
            params = Utility.json_loads(record["body"]).get("params", {})

            self.logger.info(
                f"(SQS) Endpoint ID: {endpoint_id}, Function: {funct}, Params: {Utility.json_dumps(params)}"
            )
            self.dispatch(endpoint_id, funct, params=params)

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

        endpoint_id, funct = pieces[0], pieces[1]
        self.logger.info(
            f"(S3) Endpoint ID: {endpoint_id}, Function: {funct}, Params: {Utility.json_dumps(params)}"
        )
        self.dispatch(endpoint_id, funct, params=params)

    def _handle_dynamodb_event(self, event: Dict[str, Any]) -> None:
        """Handle DynamoDB events."""
        endpoint_id = os.getenv("DYNAMODBSTREAMENDPOINTID", "")
        funct = "stream_handle"
        params = {"records": event.get("Records", [])}

        table_name = self.extract_table_name(event["Records"][0]["eventSourceARN"])
        dynamodb_stream_config = LambdaBase.get_setting("dynamodb_stream_config")

        if not dynamodb_stream_config.get(table_name):
            self.logger.info(
                f"(DynamoDB) Endpoint ID: {endpoint_id}, Function: {funct}, Params: {Utility.json_dumps(params)}"
            )
            self.dispatch(endpoint_id, funct, params=params)
        else:
            for config in dynamodb_stream_config[table_name]:
                self.logger.info(
                    f"(DynamoDB) Endpoint ID: {config['endpoint_id']}, Function: {config['funct']}, Params: {Utility.json_dumps(params)}"
                )
                self.dispatch(config["endpoint_id"], config["funct"], params=params)

    def _handle_bot_event(self, event: Dict[str, Any]) -> None:
        """Handle bot events."""
        endpoint_id = event["bot"]["id"]
        funct = f"{event['bot']['name'].lower()}_lex_dispatch"
        params = event

        self.logger.info(
            f"(Lex Bot) Endpoint ID: {endpoint_id}, Function: {funct}, Params: {Utility.json_dumps(params)}"
        )
        self.dispatch(endpoint_id, funct, params=params)
