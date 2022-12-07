#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from silvaengine_base.lambdabase import LambdaBase
from silvaengine_utility import Utility, Authorizer as ApiGatewayAuthorizer
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
import json, traceback, jsonpickle, sentry_sdk

__author__ = "bibow"


class Resources(LambdaBase):
    settings = {}

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger
        self.init()

    def handle(self, event, context):
        try:
            ### ! 1. Trigger Cognito hooks.
            if event and event.get("triggerSource") and event.get("userPoolId"):
                # settings = LambdaBase.get_setting("event_triggers")

                fn = Utility.import_dynamically(
                    # module_name="event_triggers",
                    module_name=self.settings.get(
                        "cognito_hooks_module_name",
                        "event_triggers",
                    ),
                    function_name=self.settings.get(
                        "cognito_hooks_function_name",
                        "pre_token_generate",
                    ),
                    class_name=self.settings.get(
                        "cognito_hooks_class_name",
                        "Cognito",
                    ),
                    constructor_parameters=dict(
                        {"logger": self.logger},
                        **self.settings,
                    ),
                )

                if callable(fn):
                    return fn(event, context)

            headers = event.get("headers", {})
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
                    if not event.get("queryStringParameters")
                    else {}
                ),
            )
            method = (
                request_context.get("httpMethod")
                if not request_context.get("httpMethod")
                else event.get("httpMethod")
                if not event.get("httpMethod")
                else "POST"
            )
            setting_id = "{stage}_{area}_{endpoint_id}".format(
                stage=request_context.get("stage", "beta"),
                area=area,
                endpoint_id=endpoint_id,
            )

            ### ? 1.1. Get global settings from se-configdata.
            global_settings = LambdaBase.get_setting(setting_id=setting_id)

            # if global_settings.get("enable_api_unified_call", False):
            # proxy_path = (
            #     str(global_settings.get("graphql_proxy_path", "graphql"))
            #     .strip()
            #     .lower()
            # )

            # if proxy_path == str(funct).strip().lower():
            proxy_index = str(global_settings.get("api_unified_call_index", "")).strip()

            if headers.get(proxy_index):
                funct = str(headers.get(proxy_index)).strip()

            ### ! 2. Get function settings.
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
                    "headers": headers,
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

            ### ! 3. Authorize
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

            ### ! 4. Transfer the request to the lower-level logic
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

            result = LambdaBase.invoke(
                function.aws_lambda_arn,
                payload,
                invocation_type=str(function.config.funct_type).strip(),
            )

            response = jsonpickle.decode(result)
            status_code = response.pop("status_code", 200)

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
            request_context = event.get("requestContext", {})
            arn = event.get("methodArn", {})
            path_parameters = event.get("pathParameters", {})
            area = path_parameters.get("area")
            endpoint_id = path_parameters.get("endpoint_id")
            stage = request_context.get("stage")

            if len(e.args) > 1 and type(e.args[1]) is int:
                status_code = e.args[1]

            if message is None:
                message = log

            if str(event.get("type")).strip().lower() == "request":
                principal = event.get("path")
                aws_account_id = request_context.get("accountId")
                api_id = request_context.get("apiId")
                region = arn.split(":")[3]
                ctx = {"error_message": message}

                return ApiGatewayAuthorizer(
                    principal=principal,
                    aws_account_id=aws_account_id,
                    api_id=api_id,
                    region=region,
                    stage=stage,
                ).authorize(is_allow=False, context=ctx)

            if str(status_code).startswith("5"):
                settings = LambdaBase.get_setting(
                    "{}_{}_{}".format(stage, area, endpoint_id)
                )

                if settings.get("sentry_enabled", False):
                    sentry_sdk.capture_exception(e)

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

    def init(self):
        self.settings = LambdaBase.get_setting("general")
        sentry_enabled = self.settings.get("sentry_enabled", False)
        sentry_dsn = self.settings.get("sentry_dsn")

        if sentry_enabled and sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[
                    AwsLambdaIntegration(),
                ],
                # Set traces_sample_rate to 1.0 to capture 100%
                # of transactions for performance monitoring.
                # We recommend adjusting this value in production,
                traces_sample_rate=float(
                    self.settings.get("sentry_traces_sample_rate", 1.0)
                ),
            )
