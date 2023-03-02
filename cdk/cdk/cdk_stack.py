import os
from aws_cdk import core as cdk

from aws_cdk import (
    core,
    aws_datasync as datasync,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_applicationautoscaling as appScaling,
    aws_s3 as s3,
)
from cdk_valheim import ValheimWorld, ValheimWorldScalingSchedule


class CdkStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # The code that defines your stack goes here
        self.valheim_world = ValheimWorld(
            self,
            "ValheimWorld",
            cpu=2048,
            memory_limit_mib=4096,
            schedules=[
                ValheimWorldScalingSchedule(
                    start=appScaling.CronOptions(hour="12", week_day="1-5"),
                    stop=appScaling.CronOptions(hour="1", week_day="1-5"),
                )
            ],
            environment={
                "SERVER_NAME": os.environ.get("SERVER_NAME", "CDK Valheim"),
                "WORLD_NAME": os.environ.get("WORLD_NAME", "Amazon"),
                "SERVER_PASS": os.environ.get("SERVER_PASS", "fargate"),
                "BACKUPS": "false",
            },
        )

        self.env_vars = {
            "APPLICATION_PUBLIC_KEY": os.environ.get("APPLICATION_PUBLIC_KEY"),
            "ECS_SERVICE_NAME": self.valheim_world.service.service_name,
            "ECS_CLUSTER_ARN": self.valheim_world.service.cluster.cluster_arn,
        }

        self.flask_lambda_layer = _lambda.LayerVersion(
            self,
            "FlaskAppLambdaLayer",
            code=_lambda.AssetCode("./layers/flask"),
            compatible_runtimes=[
                _lambda.Runtime.PYTHON_3_8,
            ],
        )

        self.flask_app_lambda = _lambda.Function(
            self,
            "FlaskAppLambda",
            runtime=_lambda.Runtime.PYTHON_3_8,
            code=_lambda.AssetCode("./lambda/functions/interactions"),
            function_name="flask-app-handler",
            handler="lambda-handler.handler",
            layers=[self.flask_lambda_layer],
            timeout=core.Duration.seconds(60),
            environment={**self.env_vars},
        )

        self.flask_app_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                self,
                "ECS_FullAccessPolicy",
                managed_policy_arn="arn:aws:iam::aws:policy/AmazonECS_FullAccess",
            )
        )

        # https://slmkitani.medium.com/passing-custom-headers-through-amazon-api-gateway-to-an-aws-lambda-function-f3a1cfdc0e29
        self.request_templates = {
            "application/json": """{
                "method": "$context.httpMethod",
                "body" : $input.json("$"),
                "headers": {
                    #foreach($param in $input.params().header.keySet())
                    "$param": "$util.escapeJavaScript($input.params().header.get($param))"
                    #if($foreach.hasNext),#end
                    #end
                }
            }
            """
        }

        self.apigateway = apigw.RestApi(
            self,
            "FlaskAppEndpoint",
        )

        self.apigateway.root.add_method("ANY")

        self.discord_interaction_webhook = self.apigateway.root.add_resource("discord")

        self.discord_interaction_webhook_integration = apigw.LambdaIntegration(
            self.flask_app_lambda, request_templates=self.request_templates
        )

        self.discord_interaction_webhook.add_method(
            "POST", self.discord_interaction_webhook_integration
        )
