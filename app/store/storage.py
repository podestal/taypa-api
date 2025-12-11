from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class R2Storage(S3Boto3Storage):
    """Custom storage class for Cloudflare R2 - uses AWS_* settings configured in base.py"""
    file_overwrite = False
    
    def url(self, name):
        """
        Override to use the public R2 URL instead of signed URLs.
        
        IMPORTANT: CLOUDFLARE_R2_MAIN_URL must be the full public URL, e.g.:
        https://pub-298b15d30a4a4c8b8bfd457d07eef0ec.r2.dev
        NOT just the bucket name!
        """
        if not name:
            return ''
        
        # Use the public URL if configured
        if hasattr(settings, 'CLOUDFLARE_R2_MAIN_URL') and settings.CLOUDFLARE_R2_MAIN_URL:
            main_url = settings.CLOUDFLARE_R2_MAIN_URL.rstrip('/')
            
            # Ensure name doesn't start with /
            name = name.lstrip('/')
            
            # Remove bucket name from path if it's included
            # The path might be stored as "bucket-name/dishes/file.png" but public URL should be "dishes/file.png"
            parts = name.split('/')
            if len(parts) > 1:
                # Check if first part is a bucket name
                # Common bucket names to remove: configured bucket, rodriguez-zea, signatum-storage
                possible_bucket_names = []
                if hasattr(settings, 'CLOUDFLARE_R2_BUCKET') and settings.CLOUDFLARE_R2_BUCKET:
                    possible_bucket_names.append(settings.CLOUDFLARE_R2_BUCKET)
                possible_bucket_names.extend(['rodriguez-zea', 'signatum-storage'])
                
                # If first part matches a bucket name, remove it
                if parts[0] in possible_bucket_names:
                    name = '/'.join(parts[1:])  # Remove bucket name, keep rest of path
            
            # Construct the full public URL
            # If main_url doesn't start with http:// or https://, it's probably just a bucket name
            # In that case, the URL will be wrong - user needs to fix CLOUDFLARE_R2_MAIN_URL
            return f"{main_url}/{name}"
        
        # Fallback to parent implementation (signed URL)
        return super().url(name)

