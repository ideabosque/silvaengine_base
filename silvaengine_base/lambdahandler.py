#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = 'bibow'

import sys
sys.path.append('/opt')

import json, os, boto3, traceback
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal
from silvaengine_utility import Utility


class LambdaBase(object):

    aws_lambda = boto3.client('lambda')
    dynamodb = boto3.resource('dynamodb')

    @classmethod
    def get_handler(cls, *args, **kwargs):
        def handler(event, context):
            return cls(*args, **kwargs).handle(event, context)
        return handler

    def handle(self, event, context):
        raise NotImplementedError

    @classmethod
    def invoke(cls, function_name, payload, invocation_type="Event"):
        response = cls.aws_lambda.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload),
        )
        if "FunctionError" in response.keys():
            log = json.loads(response['Payload'].read())
            raise Exception(log)
        if invocation_type == "RequestResponse":
            return json.loads(response['Payload'].read())

    @classmethod
    def get_item(cls, table, **key):
        try:
            table_name = "se-{table}".format(table=table)
            response = cls.dynamodb.Table(table_name).get_item(
                Key=key
            )
        except ClientError:
            raise
        else:
            item = response.get("Item", None)
            if item is None:
                log = "Cannot find the item with the key({0})".format(key)
                raise Exception(log)
            return item

    @classmethod
    def get_setting(cls, setting_id):
        if setting_id == '':
            return {}
        try:
            response = cls.dynamodb.Table("se-configdata").query(
                KeyConditionExpression=Key('setting_id').eq(setting_id)
            )
        except ClientError:
            raise
        else:
            assert response['Count'] > 0, "Cannot find values with the setting_id({0})".format(setting_id)
            return dict(
                (
                    item['variable'], 
                    item['value']
                ) for item in response.get("Items")
            )

    @classmethod
    def get_function(cls, endpoint_id, funct, api_key="#####", method=None):
        # If a task calls this function, the special_connection should be TRUE.
        if endpoint_id != "0":
            endpoint = cls.get_item(
                "endpoints", **{
                    "endpoint_id": endpoint_id
                }
            )
            endpoint_id = endpoint_id if endpoint.get("special_connection") else "1"
            
        connection = cls.get_item("connections", **{
            "endpoint_id": endpoint_id,
            "api_key": api_key            
        })
        functs = list(filter(lambda x: x["function"]==funct, connection["functions"]))

        assert len(functs) == 1, \
            "Cannot find the function({funct}) with endpoint_id({endpoint_id}) and api_key({api_key}).".format(
                funct=funct, 
                endpoint_id=endpoint_id, 
                api_key=api_key
            )

        function = cls.get_item("functions", **{
            "aws_lambda_arn": functs[0]["aws_lambda_arn"],
            "function": functs[0]["function"]
        })

        ## Merge the setting in connection and function
        ## (the setting in the funct of a connection will override the setting in the function).
        setting = dict(
            cls.get_setting(
                function["config"].get("setting")
            ), 
            **cls.get_setting(
                functs[0].get("setting")
            )
        )
        
        if method is not None:
            assert method in function["config"]["methods"], \
                "The function({funct}) doesn't support the method({method}).".format(
                    funct=funct, 
                    method=method
                )

        return (setting, function)


class Resources(LambdaBase):

    def __init__(self, logger): # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        # TODO implement
        try:
            area = event['pathParameters']['area']
            method = event["httpMethod"]
            endpoint_id = event['pathParameters']['endpoint_id']
            funct = event['pathParameters']['proxy']
            params = dict(
                {"endpoint_id": endpoint_id, "area": area},
                **(event['queryStringParameters'] if event['queryStringParameters'] is not None else {})
            )
            body = event['body']
            api_key = event['requestContext']['identity']['apiKey']
            self.logger.info([endpoint_id, funct, api_key, method])

            (setting, function) = LambdaBase.get_function(endpoint_id, funct, api_key=api_key, method=method)
            
            assert (function is not None and setting is not None) and area == function.get("area"), \
                "Cannot locate the function!!.  Please check the path and parameters."
            
            payload = {
                "MODULENAME": function["config"]["moduleName"],
                "CLASSNAME": function["config"]["className"],
                "funct": function["function"],
                "setting": json.dumps(setting),
                "params": json.dumps(params),
                "body": body
            }
            res = LambdaBase.invoke(
                function["aws_lambda_arn"],
                payload,
                invocation_type=function["config"]["functType"]
            )
            return {
                "statusCode": 500 if funct.find('graphql') != -1 and 'errors' in Utility.json_loads(res).keys() else 200,
                "headers": {
                    'Access-Control-Allow-Headers': 'Access-Control-Allow-Origin',
                    'Access-Control-Allow-Origin': '*'
                },
                "body": res
            }

        except Exception:
            log = traceback.format_exc()
            self.logger.exception(log)
            return {
                "statusCode": 500,
                'headers': {
                    'Access-Control-Allow-Headers': 'Access-Control-Allow-Origin',
                    'Access-Control-Allow-Origin': '*'
                },
                "body": (
                    json.dumps({"error": "{0}".format(log)}, indent=4)
                )
            }


class Tasks(LambdaBase):

    sqs = boto3.client('sqs')
    sns = boto3.client("sns")

    def __init__(self, logger): # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    @classmethod
    def get_queue_attributes(cls, queue_url=None):
        response = cls.sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['All']
        )
        attributes = response["Attributes"]
        total_messages = int(attributes["ApproximateNumberOfMessages"]) + \
            int(attributes["ApproximateNumberOfMessagesNotVisible"]) + \
            int(attributes["ApproximateNumberOfMessagesDelayed"])
        attributes["TotalMessages"] = total_messages
        return attributes

    @classmethod
    def fetch_queue_messages(cls, queue_name, logger):
        messages = []
        total_messages = 0
        queue_url = None

        try:
            response = cls.sqs.get_queue_url(QueueName=queue_name)
            queue_url = response['QueueUrl']

            total_messages = cls.get_queue_attributes(queue_url=queue_url)["TotalMessages"]
            if total_messages != 0:
                response = cls.sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=int(os.environ["SQSMAXMSG"]),
                    VisibilityTimeout=600
                )
                for message in response('Messages',[]):
                    messages.append(json.loads(message['Body']))
                    cls.sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    total_messages = total_messages - 1
                    logger.debug(message['Body'])
            if total_messages == 0:
                cls.sqs.delete_queue(QueueUrl=queue_url)
                logger.debug('"{queue_url}" is deleted.'.format(queue_url=queue_url))
        except ClientError as e:
            if e.response['Error']['Code'] not in ('AWS.SimpleQueueService.NonExistentQueue'):
                raise

        return (queue_url, messages, total_messages)

    @classmethod
    def dispatch(cls, endpoint_id, funct, params=None):
        (setting, function) = cls.get_function(endpoint_id, funct)
        assert function is not None and setting is not None, \
            "Cannot locate the function!!.  Please check the path and parameters."

        payload = {
            "MODULENAME": function["config"]["moduleName"],
            "CLASSNAME": function["config"]["className"],
            "funct": function["function"],
            "setting": json.dumps(setting),
            "params": json.dumps(params),
        }
        
        cls.invoke(
            function["aws_lambda_arn"],
            payload,
            invocation_type=function["config"]["functType"]
        )


    def handle(self, event, context):
        # TODO implement

        try:
            queue_name = event.get('queue_name')
            endpoint_id = event.get('endpoint_id')

            if queue_name is not None:
                try:
                    (queue_url, messages, total_messages) = Tasks.fetch_queue_messages(queue_name, self.logger)
                    
                    if len(messages) > 0:
                        funct = event.get('funct')
                        Tasks.dispatch(endpoint_id, funct, params={"data": messages})
                        self.logger.info("endpoint_id: {endpoint_id}, funct: {funct}".format(
                                endpoint_id=endpoint_id, 
                                funct=funct
                            )
                        )

                except Exception:
                    log = traceback.format_exc()
                    self.logger.exception(log)
                    Tasks.invoke(
                        context.invoked_function_arn,
                        event
                    )
                    return

                self.logger.info('queue_url: {queue_url}, processed_messages: {processed_messages}, total_messages: {total_messages}'.format(
                        queue_url=queue_url,
                        processed_messages=len(messages),
                        total_messages=total_messages
                    )
                )
                if queue_url is not None:
                    if total_messages == 0:
                        funct = "updateSyncTask"
                        Tasks.dispatch(endpoint_id, funct, params={"id": queue_name})
                        self.logger.info("endpoint_id: {endpoint_id}, funct: {funct}".format(
                                endpoint_id=endpoint_id, 
                                funct=funct
                            )
                        )
                    else:
                        Tasks.invoke(
                            context.invoked_function_arn,
                            event
                        )
            else:
                funct = event.get('funct')
                params = event.get('params')
                Tasks.dispatch(endpoint_id, funct, params=params)
                self.logger.info("endpoint: {endpoint_id}, funct: {funct}".format(
                        endpoint_id=endpoint_id, 
                        funct=funct
                    )
                )

        except Exception:
            log = traceback.format_exc()
            self.logger.exception(log)
            if 'SNSTOPICARN' in os.environ.keys():
                Tasks.sns.publish(
                    TopicArn=os.environ["SNSTOPICARN"],
                    Subject=context.invoked_function_arn,
                    MessageStructure="json",
                    Message= json.dumps({"default": log})
                )

class Worker(LambdaBase):

    last_request_id = None
    
    @classmethod
    def set_last_request_id(cls, aws_request_id):
        if cls.last_request_id == aws_request_id:
            return # abort
        else:
            cls.last_request_id = aws_request_id

    def __init__(self, logger): # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    def handle(self, event, context):
        # TODO implement
        Worker.set_last_request_id(context.aws_request_id)

        _class = getattr(
            __import__(event.get("MODULENAME")),
            event.get("CLASSNAME")
        )

        funct = getattr(
            _class(self.logger, **json.loads(event.get("setting"))),
            event.get("funct")
        )

        params = event.get('params')
        body = event.get('body')
        
        if params is None and body is None:
            return funct()

        params = dict(
            (k,v) for k,v in dict(
                ({} if params is None else json.loads(params,parse_float=Decimal)),
                **({} if body is None else json.loads(body,parse_float=Decimal))
            ).items() if v is not None and v != ''
        )

        return funct(**params)