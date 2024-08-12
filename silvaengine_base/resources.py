#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from silvaengine_base.lambdabase import LambdaBase, FunctionError
from silvaengine_utility import Utility, Authorizer as ApiGatewayAuthorizer
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
from datetime import datetime
import ujson, json, traceback, sentry_sdk, yaml, random, string

__author__ = "bibow"

def generate_random_string(length):
    all_characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(all_characters) for _ in range(length))
    return random_string

def runtime_debug(r, t, s):
    d = int(datetime.now().timestamp() * 1000) - t

    # if d > 400:
    if str(s).strip().lower() == "ss3":
        print("--------- It took {} ms to execute request `{}`.".format(d, r))


def is_yaml(content,s):
    try:
        js = int(datetime.now().timestamp() * 1000)
        # Try loading the content as YAML
        yaml.load(content, Loader=yaml.SafeLoader)
        runtime_debug(" -------------- Check if the content is YAML.", js,s)
        return True
    except yaml.YAMLError:
        return False


def is_json(content,s):
    try:
        js = int(datetime.now().timestamp() * 1000)
        json.loads(content)
        runtime_debug(" -------------- Check if the content is JSON.", js,s)
        return True
    except ValueError:
        return False


class Resources(LambdaBase):
    settings = {}

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        # self.settings = LambdaBase.get_setting("general")
        self.logger = logger

    def handle(self, event, context):
        try:
            req = generate_random_string(8)
            est = int(datetime.now().timestamp() * 1000)

            ### ! init
            if len(self.settings) < 1:
                self.init(event=event)
                # runtime_debug(req+":init(1)", est)

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
                    resp = fn(event, context)
                    # runtime_debug(req+":pre_token_generate(2)", est)
                    return resp

            headers = event.get("headers", {})
            request_context = event.get("requestContext", {})
            api_key = request_context.get("identity", {}).get("apiKey")

            path_parameters = event.get("pathParameters", {})
            area = path_parameters.get("area")
            endpoint_id = path_parameters.get("endpoint_id")
            params = dict(
                {"endpoint_id": endpoint_id, "area": area},
                **(
                    event.get("queryStringParameters", {})
                    if event.get("queryStringParameters")
                    else {}
                ),
            )

            proxy = path_parameters.get("proxy")
            index = proxy.find("/")
            funct = proxy[:index] if index != -1 else proxy

            if index != -1:
                params.update(
                    {
                        "path": proxy[index + 1 :],
                    }
                )

            method = (
                request_context.get("httpMethod")
                if request_context.get("httpMethod")
                else event.get("httpMethod") if event.get("httpMethod") else "POST"
            )
            # setting_id = "{stage}_{area}_{endpoint_id}".format(
            #     stage=request_context.get("stage", "beta"),
            #     area=area,
            #     endpoint_id=endpoint_id,
            # )

            ### ? 1.1. Get global settings from se-configdata.
            # global_settings = LambdaBase.get_setting(setting_id=setting_id)

            # if global_settings.get("enable_api_unified_call", False):
            # proxy_path = (
            #     str(global_settings.get("graphql_proxy_path", "graphql"))
            #     .strip()
            #     .lower()
            # )

            # if proxy_path == str(funct).strip().lower():
            proxy_index = str(self.settings.get("api_unified_call_index", "")).strip()

            if headers.get(proxy_index):
                funct = str(headers.get(proxy_index)).strip()

            ### ! 2. Get function settings.
            (setting, function) = LambdaBase.get_function(
                endpoint_id, funct, api_key=api_key, method=method
            )
            # runtime_debug(req+":get_function(3)", est)

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
                    resp = fn(event, context)
                    # runtime_debug(req+":authorize(4)", est)
                    return resp
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
                    # runtime_debug(req+":verify_permission(5)", est)

            ### ! 4. Transfer the request to the lower-level logic
            js = int(datetime.now().timestamp() * 1000)
            payload = {
                "MODULENAME": function.config.module_name,
                "CLASSNAME": function.config.class_name,
                "funct": function.function,
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": event.get("body"),
                "context": json.loads(request_context),
            }

            runtime_debug(req+" ------------- build payload (Twice json dump)", js, endpoint_id)

            if str(function.config.funct_type).strip().lower() == "event":
                LambdaBase.invoke(
                    function.aws_lambda_arn,
                    payload,
                    invocation_type="Event",
                )

                # runtime_debug(req+":invoke event(6)", est)

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

            # Prepare headers based on the content type
            headers = {
                "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                "Access-Control-Allow-Origin": "*",
            }

            
            # if is_yaml(result, endpoint_id):
            #     headers["Content-Type"] = "application/x-yaml"
            #     status_code = 200
            #     body = result  # Assuming the YAML content is already a string
            # el
            if is_json(result, endpoint_id):
                js = int(datetime.now().timestamp() * 1000)
                headers["Content-Type"] = "application/json"
                try:
                    response = json.loads(result)
                    status_code = response.pop("status_code", 200)
                    body = json.dumps(response)  # Convert the modified response back to a JSON string
                except:
                    # If decoding somehow still fails, return an error (this should be rare given the is_json check)
                    status_code = 400  # Bad Request
                    body = '{"error": "Failed to decode JSON"}'
                runtime_debug(req+" ------------- build response (jsonpickle encode & decode)", js, endpoint_id)
            elif type(result) is FunctionError:
                # If content is neither YAML nor JSON, handle accordingly
                status_code = 500 # Bad Request or consider another appropriate status code
                body = '{"error": '+result.args[0]+'}'
                headers["Content-Type"] = "application/json"
            elif is_yaml(result, endpoint_id):
                headers["Content-Type"] = "application/x-yaml"
                status_code = 200
                body = result  # Assuming the YAML content is already a string
            else:
                # If content is neither YAML nor JSON, handle accordingly
                status_code = 400 # Bad Request or consider another appropriate status code
                body = '{"error": "Unsupported content format"}'
                headers["Content-Type"] = "application/json"

            
            # runtime_debug(req+":invoke request(7)", est)
            
            return {
                "statusCode": status_code,
                "headers": headers,
                "body": body,
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

            # runtime_debug(req+":exception(7)", est)

            if str(event.get("type")).strip().lower() == "request":
                principal = event.get("path")
                aws_account_id = request_context.get("accountId")
                api_id = request_context.get("apiId")
                region = arn.split(":")[3]
                context = {"error_message": message}

                return ApiGatewayAuthorizer(
                    principal=principal,
                    aws_account_id=aws_account_id,
                    api_id=api_id,
                    region=region,
                    stage=stage,
                ).authorize(is_allow=False, context=context)

            if str(status_code).startswith("5"):
                if len(self.settings) < 1:
                    self.init(event=event)

                if self.settings.get("sentry_enabled", False):
                    sentry_sdk.capture_exception(e)

            js = int(datetime.now().timestamp() * 1000)
            body = json.dumps({"error": message})
            runtime_debug(req+" ------------- json dumps body of response", js, endpoint_id)

            return {
                "statusCode": int(status_code),
                "headers": {
                    "Access-Control-Allow-Headers": "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": body,
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

    # Get setting index of config data
    def get_setting_index(self, event):
        try:
            if event:
                if event.get("triggerSource") and event.get("userPoolId"):
                    settings = LambdaBase.get_setting("general")

                    if settings:
                        index = settings.get(event.get("userPoolId"))

                        if index:
                            return index
                elif event.get("requestContext") and event.get("pathParameters"):
                    request_context = event.get("requestContext", {})
                    path_parameters = event.get("pathParameters", {})
                    area = path_parameters.get("area")
                    endpoint_id = path_parameters.get("endpoint_id")
                    stage = request_context.get("stage", "beta")

                    if area and endpoint_id and stage:
                        return "{}_{}_{}".format(stage, area, endpoint_id)

            # raise Exception("Invalid event request")
        except Exception as e:
            raise e

    def init(self, event):
        ### ! Load settings from config data
        self.settings = LambdaBase.get_setting(self.get_setting_index(event=event))

        ### ! Init sentry
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
