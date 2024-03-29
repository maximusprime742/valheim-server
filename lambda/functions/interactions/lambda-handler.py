import os
import logging

import awsgi
import boto3
from discord_interactions import verify_key_decorator
from flask import Flask, jsonify, request


client = boto3.client("ecs")

# Your public key can be found on your application in the Developer Portal
PUBLIC_KEY = os.environ.get("APPLICATION_PUBLIC_KEY")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

app = Flask(__name__)


@app.route("/discord", methods=["POST"])
@verify_key_decorator(PUBLIC_KEY)
def index():
    if request.json["type"] == 1:
        return jsonify({"type": 1})
    else:
        logger.info(request.json)
        try:
            interaction_option = request.json["data"]["options"][0]["value"]
        except KeyError:
            logger.info("Could not parse the interaction option")
            interaction_option = "status"

        logger.info("Interaction:")
        logger.info(interaction_option)

        content = ""

        if interaction_option == "status":
            try:
                resp = client.describe_services(
                    cluster=os.environ.get("ECS_CLUSTER_ARN", ""),
                    services=[
                        os.environ.get("ECS_SERVICE_NAME", ""),
                    ],
                )
                desired_count = resp["services"][0]["desiredCount"]
                running_count = resp["services"][0]["runningCount"]
                pending_count = resp["services"][0]["pendingCount"]

                content = f"Desired: {desired_count} | Running: {running_count} | Pending: {pending_count}"

            except Error as e:
                content = " | Could not get server status"
                logger.info("Could not get the server status")
                logger.info(e)

            try:
                task_list = client.list_tasks(
                    cluster=os.environ.get("ECS_CLUSTER_ARN" "")
                )

                if task_list is not []:
                    task_arn = task_list[0]

                    resp2 = client.describe_tasks(
                        cluster=os.environ.get("ECS_CLUSTER_ARN", ""),
                        tasks=[
                            task_arn,
                        ],
                    )

                    eni_id = resp2["tasks"][0]["attachments"][0]["details"][1]["value"]

                    eni = boto3.resource("ec2").NetworkInterface(eni_id)

                    public_ip = eni.association_attribute["PublicIp"]

                    content += f" | Pubilc IP: {public_ip}"

            except Exception as e:
                content += "Could not get server ip"
                logger.info("Could not get server ip")
                logger.info(e)

        elif interaction_option == "start":
            content = "Starting the server"

            resp = client.update_service(
                cluster=os.environ.get("ECS_CLUSTER_ARN", ""),
                service=os.environ.get("ECS_SERVICE_NAME", ""),
                desiredCount=1,
            )

        elif interaction_option == "stop":
            content = "Stopping the server"

            resp = client.update_service(
                cluster=os.environ.get("ECS_CLUSTER_ARN", ""),
                service=os.environ.get("ECS_SERVICE_NAME", ""),
                desiredCount=0,
            )

        else:
            content = "Unknown command"

        logger.info(resp)

        return jsonify(
            {
                "type": 4,
                "data": {
                    "tts": False,
                    "content": content,
                    "embeds": [],
                    "allowed_mentions": {"parse": []},
                },
            }
        )


def handler(event, context):
    return awsgi.response(app, event, context, base64_content_types={"image/png"})
