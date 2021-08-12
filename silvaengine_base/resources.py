#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import json, traceback, asyncio
from .lambdabase import LambdaBase
from silvaengine_auth import Auth
from event_triggers import Cognito
from silvaengine_utility import Utility
from importlib.util import find_spec
from importlib import import_module

# from event_recorder import Recorder


class Resources(LambdaBase):
    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        # TODO implement
        try:
            # Trigger hooks
            if event and event.get("triggerSource") and event.get("userPoolId"):
                settings = LambdaBase.get_setting("event_triggers")

                return Cognito(self.logger, **settings).pre_token_generate(
                    event, context
                )

            area = event["pathParameters"]["area"]
            api_key = event["requestContext"]["identity"]["apiKey"]
            endpoint_id = event["pathParameters"]["endpoint_id"]
            funct = event["pathParameters"]["proxy"]
            params = dict(
                {"endpoint_id": endpoint_id, "area": area},
                **(
                    event["queryStringParameters"]
                    if event["queryStringParameters"] is not None
                    else {}
                ),
            )
            method = (
                event.get("requestContext").get("httpMethod")
                if event.get("requestContext").get("httpMethod")
                else event["httpMethod"]
            )

            (setting, function) = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )

            assert (
                area == function.area
            ), f"Area ({area}) is not matched the configuration of the function ({funct}).  Please check the parameters."

            event.update(
                {"fnConfigurations": Utility.json_loads(Utility.json_dumps(function))}
            )

            print("ORIGIN REQUEST:", event)

            # If auth_required is True, validate authorization.
            # If graphql, append the graphql query path to the path.
            if str(event.get("type")).lower() == "request":
                return Auth(self.logger).authorize(event, context)
            elif event.get("body"):
                event.update(Auth(self.logger).verify_permission(event, context))

            payload = {
                "MODULENAME": function.config.module_name,
                "CLASSNAME": function.config.class_name,
                "funct": function.function,
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": event["body"],
                "context": Utility.json_dumps(event["requestContext"]),
            }

            if function.config.funct_type == "Event":
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type=function.config.funct_type,
                )

                return {
                    "statusCode": 200,
                    "headers": {
                        "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": "",
                }

            res = Utility.json_loads(
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type=function.config.funct_type,
                )
            )
            status_code = res.pop("status_code", 200)

            return {
                "statusCode": status_code,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": Utility.json_dumps(res),
            }

        except Exception as e:
            log = traceback.format_exc()
            self.logger.exception(log)
            message = e.args[0]
            status_code = 500

            if len(e.args) > 1:
                status_code = e.args[1]

            if message is None:
                message = log

            print("SilvaEngine Base exception:", status_code, message, type(message))
            return {
                "statusCode": status_code,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": Utility.json_dumps({"error": message}),
            }

    # Exec hooks
    # If returns True, break exec
    def trigger_hooks(self, event, context):
        # 1. Get hooks from settings
        api_id = event.get("requestContext").get("apiId")

        if api_id is None:
            raise Exception("API ID is invalid", 500)

        hooks = LambdaBase.get_hooks(api_id)
        aysnc_hooks = []

        # 2. Exec hooks
        for hook in hooks:
            # 2.1. Load module by dynamic
            module_name = hook.get("module_name")
            function_name = hook.get("function_name")

            if module_name is None or function_name is None:
                continue

            spec = find_spec(module_name)

            if spec is None:
                continue

            module = import_module(module_name)

            if not hasattr(module, function_name):
                continue

            function = getattr(module, function_name)()

            if hook.get("is_async"):
                # 2.2. Add function to async queue
                aysnc_hooks.append(function)
            else:
                # 2.3. Exec hook by sync
                result = function(event, context)

                # 2.3.1. If the function returns false, it just means that the verification failed
                if result == False:
                    return result

        # 3. Exec async hooks
        if len(aysnc_hooks):

            async def exec_async_hooks(hooks):
                await asyncio.gather(*[hook(event, context) for hook in hooks])

            asyncio.run(exec_async_hooks(hooks))

        return True
