from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class R2Storage(S3Boto3Storage):
    """Custom storage class for Cloudflare R2 - uses AWS_* settings configured in base.py"""
    file_overwrite = False
    
    def url(self, name):
        """Override to use the public R2 URL instead of signed URLs"""
        if hasattr(settings, 'CLOUDFLARE_R2_MAIN_URL') and settings.CLOUDFLARE_R2_MAIN_URL:
            # Use the public URL if configured
            return f"{settings.CLOUDFLARE_R2_MAIN_URL.rstrip('/')}/{name}"
        # Fallback to endpoint URL
        return super().url(name)

