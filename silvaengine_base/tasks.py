#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "bibow"

import json, traceback, boto3, os
from botocore.exceptions import ClientError
from .lambdabase import LambdaBase


class Tasks(LambdaBase):

    sqs = boto3.client("sqs", region_name=os.getenv("REGIONNAME", "us-east-1"))
    sns = boto3.client("sns", region_name=os.getenv("REGIONNAME", "us-east-1"))

    def __init__(self, logger):  # implementation-specific args and/or kwargs
        # implementation
        self.logger = logger

    @classmethod
    def get_queue_attributes(cls, queue_url=None):
        response = cls.sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["All"]
        )
        attributes = response["Attributes"]
        total_messages = (
            int(attributes["ApproximateNumberOfMessages"])
            + int(attributes["ApproximateNumberOfMessagesNotVisible"])
            + int(attributes["ApproximateNumberOfMessagesDelayed"])
        )
        attributes["TotalMessages"] = total_messages
        return attributes

    @classmethod
    def fetch_queue_messages(cls, queue_name, logger):
        messages = []
        total_messages = 0
        queue_url = None

        try:
            response = cls.sqs.get_queue_url(QueueName=queue_name)
            queue_url = response["QueueUrl"]

            total_messages = cls.get_queue_attributes(queue_url=queue_url)[
                "TotalMessages"
            ]
            if total_messages != 0:
                response = cls.sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=int(os.environ["SQSMAXMSG"]),
                    VisibilityTimeout=600,
                )
                for message in response("Messages", []):
                    messages.append(json.loads(message["Body"]))
                    cls.sqs.delete_message(
                        QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                    )
                    total_messages = total_messages - 1
                    logger.debug(message["Body"])
            if total_messages == 0:
                cls.sqs.delete_queue(QueueUrl=queue_url)
                logger.debug(f'"{queue_url}" is deleted.')
        except ClientError as e:
            if e.response["Error"]["Code"] not in (
                "AWS.SimpleQueueService.NonExistentQueue"
            ):
                raise

        return (queue_url, messages, total_messages)

    @classmethod
    def dispatch(cls, endpoint_id, funct, params=None):
        (setting, function) = cls.get_function(endpoint_id, funct)

        payload = {
            "MODULENAME": function.config.module_name,
            "CLASSNAME": function.config.class_name,
            "funct": function.function,
            "setting": json.dumps(setting),
            "params": json.dumps(params),
        }

        cls.invoke(
            function.aws_lambda_arn,
            payload,
            invocation_type=function.config.funct_type,
        )

    def handle(self, event, context):
        # TODO implement

        try:
            queue_name = event.get("queue_name")
            endpoint_id = event.get("endpoint_id")

            if queue_name is not None:
                try:
                    (queue_url, messages, total_messages) = Tasks.fetch_queue_messages(
                        queue_name, self.logger
                    )

                    if len(messages) > 0:
                        funct = event.get("funct")
                        Tasks.dispatch(endpoint_id, funct, params={"data": messages})
                        self.logger.info(f"endpoint_id: {endpoint_id}, funct: {funct}")

                except Exception:
                    log = traceback.format_exc()
                    self.logger.exception(log)
                    Tasks.invoke(context.invoked_function_arn, event)
                    return

                processed_messages = len(messages)
                self.logger.info(
                    f"queue_url: {queue_url}, processed_messages: {processed_messages}, total_messages: {total_messages}"
                )
                if queue_url is not None:
                    if total_messages == 0:
                        funct = "updateSyncTask"
                        Tasks.dispatch(endpoint_id, funct, params={"id": queue_name})
                        self.logger.info(f"endpoint_id: {endpoint_id}, funct: {funct}")
                    else:
                        Tasks.invoke(context.invoked_function_arn, event)
            else:
                funct = event.get("funct")
                params = event.get("params")
                Tasks.dispatch(endpoint_id, funct, params=params)
                self.logger.info(f"endpoint: {endpoint_id}, funct: {funct}")

        except Exception:
            log = traceback.format_exc()
            self.logger.exception(log)
            if "SNSTOPICARN" in os.environ.keys():
                Tasks.sns.publish(
                    TopicArn=os.environ["SNSTOPICARN"],
                    Subject=context.invoked_function_arn,
                    MessageStructure="json",
                    Message=json.dumps({"default": log}),
                )
