#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from datetime import datetime
from .models import EndpointModel, ConnectionModel, FunctionModel, HookModel
from typing import Any, Dict, Tuple, List


class FunctionError(Exception):
    """Custom Exception to handle function errors."""

    pass


def runtime_debug(mark: str, start_time: int = 0) -> int:
    """
    Measure and log the execution time of a marked code block.
    :param mark: A marker to label the code block.
    :param start_time: The start time to measure the execution time.
    :return: The current timestamp in milliseconds.
    """
    current_time = int(datetime.now().timestamp() * 1000)
    if start_time > 0:
        duration = current_time - start_time
        if duration > 0:
            print(f"********** It took {duration} ms to execute `LambdaBase.{mark}`.")
    return current_time


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
        ts = runtime_debug("invoke")
        response = cls.aws_lambda.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload),
        )
        ts = runtime_debug("execute invoke", start_time=ts)

        if "FunctionError" in response:
            log = json.loads(response["Payload"].read())
            raise FunctionError(log)

        if invocation_type == "RequestResponse":
            result = json.loads(response["Payload"].read())
            runtime_debug("encode invoke result to json", start_time=ts)
            return result

    @classmethod
    def get_hooks(cls, api_id: str) -> List[Dict[str, Any]]:
        """
        Fetch active hooks for a given API ID.
        :param api_id: The ID of the API.
        :return: A list of hooks.
        """
        return [
            {item.variable: item.value}
            for item in HookModel.query(api_id, None, HookModel.status.is_(True))
        ]

    @classmethod
    def get_setting(cls, setting_id: str) -> Dict[str, Any]:
        """
        Fetch a setting from DynamoDB based on the setting ID.
        :param setting_id: The ID of the setting.
        :return: A dictionary of settings.
        """
        if not setting_id:
            return {}

        response = cls.dynamodb.Table("se-configdata").query(
            KeyConditionExpression=Key("setting_id").eq(setting_id)
        )
        if response["Count"] == 0:
            raise ValueError(f"Cannot find values with the setting_id ({setting_id}).")

        return {item["variable"]: item["value"] for item in response["Items"]}

    @classmethod
    def get_function(
        cls, endpoint_id: str, funct: str, api_key: str = "#####", method: str = None
    ) -> Tuple[Dict[str, Any], FunctionModel]:
        """
        Fetch the function configuration for a given endpoint.
        :param endpoint_id: ID of the endpoint.
        :param funct: Name of the function to retrieve.
        :param api_key: The API key, default is "#####".
        :param method: The HTTP method if applicable.
        :return: A tuple containing the merged settings and the function object.
        """
        ts = runtime_debug("get_function")
        endpoint = EndpointModel.get(endpoint_id) if endpoint_id != "0" else None
        endpoint_id = endpoint_id if (endpoint and endpoint.special_connection) else "1"
        runtime_debug("get_function: get endpoint", start_time=ts)

        connection = ConnectionModel.get(endpoint_id, api_key)
        functions = [f for f in connection.functions if f.function == funct]
        runtime_debug("get_function: get connection", start_time=ts)

        if not functions:
            raise ValueError(
                f"Cannot find the function({funct}) with endpoint_id({endpoint_id}) and api_key({api_key})."
            )

        function = FunctionModel.get(
            functions[0].aws_lambda_arn, functions[0].function
        )
        runtime_debug("get_function: get function", start_time=ts)

        if function is None:
            raise ValueError(
                "Cannot locate the function!! Please check the path and parameters."
            )

        # Merge settings from connection and function, connection settings override function settings
        setting = {
            **cls.get_setting(function.config.setting),
            **(cls.get_setting(functions[0].setting) if functions[0].setting else {}),
        }
        runtime_debug("get_function: merge setting", start_time=ts)

        if method and method not in function.config.methods:
            raise ValueError(
                f"The function({funct}) doesn't support the method({method})."
            )

        return setting, function
