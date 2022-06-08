#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from .lambdabase import LambdaBase
from silvaengine_utility import Utility, Authorizer as ApiGatewayAuthorizer
import json, traceback, jsonpickle, pendulum

__author__ = "bibow"


class Resources(LambdaBase):
    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        try:
            t = lambda: int(pendulum.now().timestamp() * 1000)
            s = t()
            f = s
            execute_analysis = []

            ### 1. Trigger hooks.
            if event and event.get("triggerSource") and event.get("userPoolId"):
                settings = LambdaBase.get_setting("event_triggers")

                fn = Utility.import_dynamically(
                    module_name="event_triggers",
                    function_name="pre_token_generate",
                    class_name="Cognito",
                    constructor_parameters=dict({"logger": self.logger}, **settings),
                )

                if callable(fn):
                    return fn(event, context)

            request_context = event.get("requestContext", {})
            path_parameters = event.get("pathParameters", {})
            area = path_parameters.get("area")
            api_key = request_context.get("identity", {}).get("apiKey")
            funct = path_parameters.get("proxy")
            endpoint_id = path_parameters.get("endpoint_id")
            params = dict(
                {"endpoint_id": endpoint_id, "area": area},
                **(
                    event.get("queryStringParameters", {})
                    if event.get("queryStringParameters") is not None
                    else {}
                ),
            )
            method = (
                request_context.get("httpMethod")
                if request_context.get("httpMethod") is not None
                else event.get("httpMethod")
                if event.get("httpMethod") is not None
                else "POST"
            )

            execute_analysis.append("1. EXECUTE HOOKS SPENT: {}".format(t() - s))
            s = t()

            ### 2. Get function settings.
            (setting, function) = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )

            assert (
                area == function.area
            ), f"Area ({area}) is not matched the configuration of the function ({funct}).  Please check the parameters."

            request_context.update(
                {
                    "channel": endpoint_id,
                    "area": area,
                }
            )
            event.update(
                {
                    "fnConfigurations": Utility.json_loads(
                        Utility.json_dumps(function)
                    ),
                    "requestContext": request_context,
                }
            )

            execute_analysis.append(
                "2. GET FUNCTION SETTINGS SPENT: {}".format(t() - s)
            )
            s = t()

            # Authorize
            if str(event.get("type")).strip().lower() == "request":
                fn = Utility.import_dynamically(
                    module_name="silvaengine_authorizer",
                    function_name="authorize",
                    class_name="Authorizer",
                    constructor_parameters=dict({"logger": self.logger}),
                )

                # If auth_required is True, validate authorization.
                if callable(fn):
                    return fn(event, context)
            elif event.get("body"):
                fn = Utility.import_dynamically(
                    module_name="silvaengine_authorizer",
                    function_name="verify_permission",
                    class_name="Authorizer",
                    constructor_parameters=dict({"logger": self.logger}),
                )

                if callable(fn):
                    # If graphql, append the graphql query path to the path.
                    event.update(fn(event, context))

            execute_analysis.append("3. AUTHORIZE SPENT: {}".format(t() - s))

            # Transfer the request to the lower-level logic
            payload = {
                "MODULENAME": function.config.module_name,
                "CLASSNAME": function.config.class_name,
                "funct": function.function,
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": event.get("body"),
                "context": jsonpickle.encode(request_context, unpicklable=False),
            }

            if str(function.config.funct_type).strip().lower() == "event":
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type="Event",
                )

                return {
                    "statusCode": 200,
                    "headers": {
                        "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": "",
                }

            s = t()

            result = LambdaBase.invoke(
                function.aws_lambda_arn,
                payload,
                invocation_type=str(function.config.funct_type).strip(),
            )

            execute_analysis.append("4. EXECUTE REQUEST SPENT: {}".format(t() - s))

            response = jsonpickle.decode(result)
            status_code = response.pop("status_code", 200)

            execute_analysis.append("5. TOTAL SPENT: {}".format(t() - s))

            if t() - f > 1500:
                print(
                    "{}\r\nModule: {}, Class: {}, Function: {}\r\n\r\n".format(
                        "*" * 80,
                        function.config.module_name,
                        function.config.class_name,
                        function.function,
                    )
                )

                for item in execute_analysis:
                    print("{}\r\n".format(item))

                print("*" * 80)

            return {
                "statusCode": status_code,
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                # "body": Utility.json_dumps(response),
                "body": result,
            }

        except Exception as e:
            log = traceback.format_exc()
            self.logger.exception(log)
            message = e.args[0]
            status_code = 500

            if len(e.args) > 1 and type(e.args[1]) is int:
                status_code = e.args[1]

            if message is None:
                message = log

            if str(event.get("type")).strip().lower() == "request":
                requestContext = event.get("requestContext", {})
                principal = event.get("path")
                aws_account_id = requestContext.get("accountId")
                api_id = requestContext.get("apiId")
                region = event.get("methodArn", {}).split(":")[3]
                stage = requestContext.get("stage")
                ctx = {"error_message": message}

                return ApiGatewayAuthorizer(
                    principal=principal,
                    aws_account_id=aws_account_id,
                    api_id=api_id,
                    region=region,
                    stage=stage,
                ).authorize(is_allow=False, context=ctx)

            return {
                "statusCode": int(status_code),
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": message}),
            }

    # Exec hooks
    def trigger_hooks(self, logger=None, settings=None, event=None, context=None):
        try:
            # print("Execute hooks")
            # # 1. Record the activity log.
            # arguments = {
            #     "module_name": "event_recorder",
            #     "function_name": "add_event_log",
            #     "class_name": "Recorder",
            #     "constructor_parameters": {"logger": logger, "setting": settings},
            # }
            # print(arguments)
            # log_recorder = Utility.import_dynamically(**arguments)

            # # 2. Call recorder by async
            # if log_recorder:
            #     print("Record event log")
            #     Utility.call_by_async(lambda: log_recorder(event))
            return None
        except Exception:
            logger.exception(traceback.format_exc())
