#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"


import json, boto3, os
from boto3.dynamodb.conditions import Key
from datetime import datetime
from .models import EndpointsModel, ConnectionsModel, FunctionsModel, HooksModel


class FunctionError(Exception):
    pass

def runtime_debug(mark, t=0):
    if t > 0:
        d = int(datetime.now().timestamp() * 1000) - t

        if d > 0:
            print("********** It took {} ms to execute `LambdaBase.{}`.".format(d, mark))

    return int(datetime.now().timestamp() * 1000)

class LambdaBase(object):
    aws_lambda = boto3.client(
        "lambda", region_name=os.getenv("REGIONNAME", "us-east-1")
    )
    dynamodb = boto3.resource(
        "dynamodb", region_name=os.getenv("REGIONNAME", "us-east-1")
    )

    @classmethod
    def get_handler(cls, *args, **kwargs):
        def handler(event, context):
            return cls(*args, **kwargs).handle(event, context)

        return handler

    def handle(self, event, context):
        raise NotImplementedError

    @classmethod
    def invoke(cls, function_name, payload, invocation_type="Event"):
        ts = runtime_debug("invoke")
        response = cls.aws_lambda.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload),
        )
        ts = runtime_debug("execute invoke",t=ts)

        if "FunctionError" in response.keys():
            log = json.loads(response["Payload"].read())
            raise FunctionError(log)
        if invocation_type == "RequestResponse":
            r= json.loads(response["Payload"].read())
            ts = runtime_debug("encode invoke result to json",t=ts)
            return r

    @classmethod
    def get_hooks(cls, api_id) -> list:
        hooks = [
            dict(
                (item.variable, item.value)
                for item in HooksModel.query(api_id, None, HooksModel.status == True)
            )
        ]

        return hooks

    @classmethod
    def get_setting(cls, setting_id):
        if setting_id == "":
            return {}

        response = cls.dynamodb.Table("se-configdata").query(
            KeyConditionExpression=Key("setting_id").eq(setting_id)
        )
        assert (
            response["Count"] > 0
        ), f"Cannot find values with the setting_id ({setting_id})."

        return {item["variable"]: item["value"] for item in response["Items"]}

    @classmethod
    def get_function(cls, endpoint_id, funct, api_key="#####", method=None):
        # If a task calls this function, the special_connection should be TRUE.
        # If special_connection is FALSE, the endpoint will be used to store the store token like shopify API; otherwise, special_connection should be TRUE.
        ts = runtime_debug("get_function")
        if endpoint_id != "0":
            endpoint = EndpointsModel.get(endpoint_id)
            endpoint_id = endpoint_id if endpoint.special_connection else "1"
            ts = runtime_debug("get_function: get endpoint",t=ts)

        if not api_key:
            api_key = "#####"

        connection = ConnectionsModel.get(endpoint_id, api_key)
        functs = list(filter(lambda x: x.function == funct, connection.functions))
        ts = runtime_debug("get_function: get connection",t=ts)

        assert (
            len(functs) == 1
        ), f"Cannot find the function({funct}) with endpoint_id({endpoint_id}) and api_key({api_key})."

        function = FunctionsModel.get(functs[0].aws_lambda_arn, functs[0].function)
        ts = runtime_debug("get_function: get function",t=ts)

        assert (
            function is not None
        ), "Cannot locate the function!!.  Please check the path and parameters."

        ## Merge the setting in connection and function
        ## (the setting in the funct of a connection will override the setting in the function).
        setting = dict(
            cls.get_setting(function.config.setting),
            **cls.get_setting(functs[0].setting) if functs[0].setting else {},
        )
        ts = runtime_debug("get_function: merge setting",t=ts)

        if method is not None:
            assert (
                method in function.config.methods
            ), f"The function({funct}) doesn't support the method({method})."

        return (setting, function)
