#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json
import boto3
import os
import time
import threading
from boto3.dynamodb.conditions import Key
from datetime import datetime
from .models import EndpointModel, ConnectionModel, FunctionModel, HookModel
from typing import Any, Dict, Tuple, List, Optional


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
            payload_str = json.dumps(payload, separators=(',', ':'))
            
            response = cls.aws_lambda.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=payload_str,
            )

            if "FunctionError" in response:
                try:
                    payload_content = response["Payload"].read()
                    log = json.loads(payload_content) if payload_content else {}
                except json.JSONDecodeError:
                    log = {"error": "Invalid JSON response from Lambda function"}
                raise FunctionError(log)

            if invocation_type == "RequestResponse":
                try:
                    payload_content = response["Payload"].read()
                    result = json.loads(payload_content) if payload_content else {}
                except json.JSONDecodeError:
                    result = {}
                return result
        except Exception as e:
            if isinstance(e, FunctionError):
                raise
            raise FunctionError(f"Failed to invoke Lambda function: {str(e)}")

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

    _setting_cache = {}
    _setting_cache_lock = threading.Lock()
    
    @classmethod
    def get_setting(cls, setting_id: str) -> Dict[str, Any]:
        """
        Fetch a setting from DynamoDB based on the setting ID with caching.
        :param setting_id: The ID of the setting.
        :return: A dictionary of settings.
        """
        if not setting_id:
            return {}

        cache_key = f"setting_{setting_id}"
        cache_ttl = 300
        
        with cls._setting_cache_lock:
            if cache_key in cls._setting_cache:
                cached_data = cls._setting_cache[cache_key]
                if time.time() - cached_data["timestamp"] < cache_ttl:
                    return cached_data["data"]
        
        try:
            response = cls.dynamodb.Table("se-configdata").query(
                KeyConditionExpression=Key("setting_id").eq(setting_id)
            )
            
            if response["Count"] == 0:
                raise ValueError(f"Cannot find values with the setting_id ({setting_id}).")
            
            setting_data = {item["variable"]: item["value"] for item in response["Items"]}
            
            with cls._setting_cache_lock:
                cls._setting_cache[cache_key] = {
                    "data": setting_data,
                    "timestamp": time.time()
                }
            
            return setting_data
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Failed to get setting {setting_id}: {str(e)}")

    _function_cache = {}
    _function_cache_lock = threading.Lock()
    
    @classmethod
    def get_function(
        cls, endpoint_id: str, funct: str, api_key: str = "#####", method: str = None
    ) -> Tuple[Dict[str, Any], FunctionModel]:
        """
        Fetch the function configuration for a given endpoint with caching.
        :param endpoint_id: ID of the endpoint.
        :param funct: Name of the function to retrieve.
        :param api_key: The API key, default is "#####".
        :param method: The HTTP method if applicable.
        :return: A tuple containing the merged settings and the function object.
        """
        if not funct:
            raise ValueError("Function name is required")
        
        cache_key = f"function_{endpoint_id}_{funct}_{api_key}_{method or ''}"
        cache_ttl = 300
        
        with cls._function_cache_lock:
            if cache_key in cls._function_cache:
                cached_data = cls._function_cache[cache_key]
                if time.time() - cached_data["timestamp"] < cache_ttl:
                    return cached_data["setting"], cached_data["function"]
        
        try:
            effective_endpoint_id = endpoint_id
            if endpoint_id != "0":
                try:
                    endpoint = EndpointModel.get(endpoint_id)
                    if not endpoint.special_connection:
                        effective_endpoint_id = "1"
                except Exception:
                    effective_endpoint_id = "1"
            else:
                effective_endpoint_id = "1"

            connection = ConnectionModel.get(effective_endpoint_id, api_key)
            
            functions = next((f for f in connection.functions if f.function == funct), None)

            if not functions:
                raise ValueError(
                    f"Cannot find the function({funct}) with endpoint_id({effective_endpoint_id}) and api_key({api_key})."
                )

            function = FunctionModel.get(
                functions.aws_lambda_arn, functions.function
            )

            if function is None:
                raise ValueError(
                    "Cannot locate the function!! Please check the path and parameters."
                )

            if method and method not in function.config.methods:
                raise ValueError(
                    f"The function({funct}) doesn't support the method({method})."
                )

            # Merge settings from connection and function, connection settings override function settings
            function_setting = cls.get_setting(function.config.setting) if function.config.setting else {}
            connection_setting = cls.get_setting(functions.setting) if functions.setting else {}
            
            setting = {
                **function_setting,
                **connection_setting,
            }
            
            with cls._function_cache_lock:
                cls._function_cache[cache_key] = {
                    "setting": setting,
                    "function": function,
                    "timestamp": time.time()
                }
            
            return setting, function
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Failed to get function {funct}: {str(e)}")
