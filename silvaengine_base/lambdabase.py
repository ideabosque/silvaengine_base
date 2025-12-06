#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import boto3, os, pendulum
from typing import Any, Dict, Tuple, List
from silvaengine_utility import Utility
from .models import EndpointModel, ConnectionModel, FunctionModel, HookModel, ConfigModel, WSSConnectionModel


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

    @classmethod
    def get_hooks(cls, api_id: str) -> List[Dict[str, Any]]:
        """
        Fetch active hooks for a given API ID.
        :param api_id: The ID of the API.
        :return: A list of hooks.
        """
        if not api_id:
            return {}
        
        try:
            return [
                {item.variable: item.value}
                for item in HookModel.query(api_id, None, HookModel.status.is_(True))
            ]
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"Failed to get hooks {api_id}: {str(e)}")

    @classmethod
    def get_setting(cls, setting_id: str) -> Dict[str, Any]:
        """
        Fetch a setting from DynamoDB based on the setting ID with caching.
        :param setting_id: The ID of the setting.
        :return: A dictionary of settings.
        """
        if not setting_id:
            return {}
        
        try:
            return {item.variable: item.value for item in ConfigModel.query_raw(setting_id).items}
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"Failed to get setting {setting_id}: {str(e)}")

    @classmethod
    def get_function(
        cls, endpoint_id: str, function_name: str, api_key: str = "#####", method: str = None
    ) -> Tuple[Dict[str, Any], FunctionModel]:
        """
        Fetch the function configuration for a given endpoint.
        :param endpoint_id: ID of the endpoint.
        :param function_name: Name of the function to retrieve.
        :param api_key: The API key, default is "#####".
        :param method: The HTTP method if applicable.
        :return: A tuple containing the merged settings and the function object.
        """
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
            
            functions = next((f for f in connection.functions if f.function == function_name), None)

            if not functions:
                raise ValueError(
                    f"Cannot find the function({function_name}) with endpoint_id({effective_endpoint_id}) and api_key({api_key})."
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
                    f"The function({function_name}) doesn't support the method({method})."
                )

            # Merge settings from connection and function, connection settings override function settings
            function_setting = cls.get_setting(function.config.setting) if function.config.setting else {}
            connection_setting = cls.get_setting(functions.setting) if functions.setting else {}
            setting = {
                **function_setting,
                **connection_setting,
            }
            
            return setting, function
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Failed to get function {function_name}: {str(e)}")

    @classmethod
    def save_wss_connection(cls, endpoint_id: str, connection_id: str, api_key: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a WSS connection model to DynamoDB.
        :param endpoint_id: The ID of the endpoint.
        :param connection_id: The ID of the connection.
        :param api_key: The API key.
        :param area: The area.
        :param data: The connection data.
        """
        try:
            return WSSConnectionModel(
                endpoint_id,
                connection_id,
                **{
                    "api_key": api_key,
                    "area": area,
                    "data": data,
                    "updated_at": pendulum.now("UTC"),
                    "created_at": pendulum.now("UTC"),
                },
            ).save()
        except Exception as e:
            raise ValueError(f"Failed to save WSS connection: {str(e)}")
        
    @classmethod
    def get_wss_connection(cls, endpoint_id: str, connection_id: str) -> WSSConnectionModel:
        """
        Get a WSS connection model from DynamoDB.
        :param endpoint_id: The ID of the endpoint.
        :param connection_id: The ID of the connection.
        :return: The WSS connection model.
        """
        try:
            return WSSConnectionModel.get(endpoint_id, connection_id)
        except Exception as e:
            raise ValueError(f"Failed to get WSS connection: {str(e)}")
        
    @classmethod
    def get_wss_connections(cls, connection_id: str) -> List[WSSConnectionModel]:
        """
        Get all WSS connection models from DynamoDB for a given connection.
        :param connection_id: The ID of the connection.
        :return: A list of WSS connection models.
        """
        try:
            return WSSConnectionModel.connect_id_index.query(connection_id)
        except Exception as e:
            raise ValueError(f"Failed to get WSS connections: {str(e)}")
        
    @classmethod
    def remove_expired_connections(cls, endpoint_id: str, email: str) -> None:
        """
        Get all WSS connection models from DynamoDB for a given endpoint.
        :param endpoint_id: The ID of the endpoint.
        :param range_condition: The range key condition.
        :param cutoff_time: The cutoff time.
        :return: A list of WSS connection models.
        """
        try:
            connections = WSSConnectionModel.query(
                hash_key=endpoint_id,
                filter_condition=WSSConnectionModel.updated_at < pendulum.now("UTC").subtract(days=1),
            )

            # Iterate through and delete matching connections
            for connection in connections:
                if (
                    email is not None
                    and connection.data.__dict__["attribute_values"].get("email") != email
                ):
                    pass

                connection.delete()
        except Exception as e:
            raise ValueError(f"Failed to get WSS connections: {str(e)}")