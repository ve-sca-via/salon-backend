"""
Setup Career Documents Storage Bucket
Creates the career-documents bucket in Supabase Storage with proper configuration
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_db_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_career_bucket():
    """Create career-documents bucket if it doesn't exist"""
    try:
        client = get_db_client()
        
        # Check if bucket exists
        buckets = client.storage.list_buckets()
        logger.info(f"📦 Found {len(buckets)} existing buckets")
        
        # Extract bucket names - handle both dict and object responses
        bucket_names = []
        for bucket in buckets:
            if isinstance(bucket, dict):
                bucket_names.append(bucket.get('name', bucket.get('id')))
            else:
                bucket_names.append(getattr(bucket, 'name', getattr(bucket, 'id', None)))
        
        logger.info(f"   Existing buckets: {', '.join(bucket_names)}")
        
        if 'career-documents' in bucket_names:
            logger.info("✅ 'career-documents' bucket already exists")
            return True
        
        # Create the bucket
        logger.info("🔨 Creating 'career-documents' bucket...")
        result = client.storage.create_bucket(
            'career-documents',
            options={
                'public': False,  # Private bucket - requires signed URLs
                'fileSizeLimit': 5242880,  # 5MB limit
                'allowedMimeTypes': [
                    'application/pdf',
                    'image/jpeg',
                    'image/jpg',
                    'image/png',
                    'image/webp',
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ]
            }
        )
        
        logger.info("✅ 'career-documents' bucket created successfully!")
        logger.info(f"   Configuration: Private, 5MB limit, 7 allowed MIME types")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting up career-documents bucket: {str(e)}")
        logger.error(f"   Error type: {type(e).__name__}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Starting career documents bucket setup...")
    success = setup_career_bucket()
    
    if success:
        logger.info("✨ Setup complete!")
        sys.exit(0)
    else:
        logger.error("💥 Setup failed!")
        sys.exit(1)
