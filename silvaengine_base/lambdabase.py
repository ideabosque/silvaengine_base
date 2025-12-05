#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import boto3
import os
from typing import Any
from silvaengine_utility import Utility


class FunctionError(Exception):
    """Custom Exception to handle function errors."""
    pass


class LambdaBase:
    REGION = os.getenv("REGIONNAME", "us-east-1")
    aws_lambda = boto3.client("lambda", region_name=REGION)
    dynamodb = boto3.resource("dynamodb", region_name=REGION)

    @classmethod
    def get_handler(cls, *args, **kwargs):
        """
        Generate a handler function for Lambda events.
        """

        def handler(event: dict, context: Any):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def handle(self, event: dict, context: Any) -> Any:
        raise NotImplementedError("Subclasses should implement this method.")

    @classmethod
    def invoke(
        cls, function_name: str, payload: dict, invocation_type: str = "Event"
    ) -> Any:
        """
        Invoke another Lambda function.
        :param function_name: Name of the Lambda function to invoke.
        :param payload: The payload to send to the Lambda function.
        :param invocation_type: Invocation type, default is "Event".
        :return: The response of the invoked Lambda function.
        """
        if not function_name:
            raise ValueError("Function name is required")
        
        valid_invocation_types = {"Event", "RequestResponse", "DryRun"}
        if invocation_type not in valid_invocation_types:
            raise ValueError(f"Invalid invocation_type: {invocation_type}")
        
        try:
            payload_str = Utility.json_dumps(payload, separators=(',', ':'))
            
            response = cls.aws_lambda.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=payload_str,
            )

            if "FunctionError" in response:
                try:
                    payload_content = response["Payload"].read()
                    log = Utility.json_loads(payload_content) if payload_content else {}
                except Exception as e:
                    log = {"error": "Invalid JSON response from Lambda function"}
                    raise FunctionError(log)

            if invocation_type == "RequestResponse":
                try:
                    payload_content = response["Payload"].read()
                    result = Utility.json_loads(payload_content) if payload_content else {}
                except Exception as e:
                    result = {}
                return result
        except Exception as e:
            if isinstance(e, FunctionError):
                raise e
            raise FunctionError(f"Failed to invoke Lambda function: {str(e)}")
