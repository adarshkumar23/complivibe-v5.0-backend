import boto3
from botocore.exceptions import ClientError


class SESEmailDeliveryService:
    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        region: str,
        from_address: str,
    ):
        self.from_address = from_address
        self.client = boto3.client(
            "ses",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> bool:
        try:
            self.client.send_email(
                Source=self.from_address,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {
                        "Html": {"Data": html_body},
                        "Text": {"Data": text_body},
                    },
                },
            )
            return True
        except ClientError:
            return False
