from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class R2Storage(S3Boto3Storage):
    """Custom storage class for Cloudflare R2 - uses AWS_* settings configured in base.py"""
    file_overwrite = False

