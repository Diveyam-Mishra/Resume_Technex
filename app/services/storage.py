import logging
import boto3
from botocore.exceptions import ClientError
import io
import uuid
import re
from typing import Optional, Union
from fastapi import HTTPException, status

from app.config.settings import settings
from app.utils.constants import ErrorMessage


logger = logging.getLogger(__name__)


class StorageService:
    """
    Service for handling storage operations with S3/MinIO.
    """
    def __init__(self):
        """
        Initialize the storage service.
        """
        self.bucket_name = settings.STORAGE_BUCKET
        
        # Initialize the S3 client
        self.client = boto3.client(
            's3',
            endpoint_url=f"{'https' if settings.STORAGE_USE_SSL else 'http'}://{settings.STORAGE_ENDPOINT}:{settings.STORAGE_PORT}",
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION,
        )
        
        # Initialize storage if not skipping bucket check
        if not settings.STORAGE_SKIP_BUCKET_CHECK:
            self._initialize_storage()

    def _initialize_storage(self):
        """
        Initialize the storage bucket and set up necessary policies.
        """
        try:
            # Check if bucket exists
            try:
                self.client.head_bucket(Bucket=self.bucket_name)
                logger.info("Successfully connected to the storage service.")
            except ClientError as e:
                # If bucket doesn't exist, create it
                if e.response['Error']['Code'] == '404':
                    self.client.create_bucket(Bucket=self.bucket_name)
                    
                    # Define a policy to allow public access to specific paths
                    policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "PublicAccess",
                                "Effect": "Allow",
                                "Action": ["s3:GetObject"],
                                "Principal": {"AWS": ["*"]},
                                "Resource": [
                                    f"arn:aws:s3:::{self.bucket_name}/*/pictures/*",
                                    f"arn:aws:s3:::{self.bucket_name}/*/previews/*",
                                    f"arn:aws:s3:::{self.bucket_name}/*/resumes/*",
                                ]
                            }
                        ]
                    }
                    
                    # Apply the policy
                    self.client.put_bucket_policy(
                        Bucket=self.bucket_name,
                        Policy=str(policy).replace("'", '"')
                    )
                    
                    logger.info("A new storage bucket has been created and the policy has been applied successfully.")
                else:
                    raise
        except Exception as e:
            logger.error(f"Error initializing storage: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="There was an error while initializing the storage service."
            )

    def bucket_exists(self) -> bool:
        """
        Check if the bucket exists.
        """
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="There was an error while checking if the storage bucket exists."
            )

    def upload_object(
        self,
        user_id: Union[str, uuid.UUID],
        type_: str,  # 'pictures', 'previews', or 'resumes'
        file_data: bytes,
        filename: Optional[str] = None
    ) -> str:
        """
        Upload an object to storage.
        
        Args:
            user_id: User ID
            type_: Type of file ('pictures', 'previews', or 'resumes')
            file_data: File data as bytes
            filename: Original filename (optional)
            
        Returns:
            URL of the uploaded file
        """
        if type_ not in ["pictures", "previews", "resumes"]:
            raise ValueError(f"Invalid file type: {type_}")
        
        extension = "pdf" if type_ == "resumes" else "jpg"
        
        # Generate a normalized filename if not provided
        if not filename:
            normalized_filename = str(uuid.uuid4())
        else:
            # Normalize the filename (convert to lowercase, replace non-alphanumeric chars with hyphens)
            normalized_filename = re.sub(r'[^a-z0-9]+', '-', filename.lower()).strip('-')
            if not normalized_filename:
                normalized_filename = str(uuid.uuid4())
        
        # Construct the filepath
        filepath = f"{user_id}/{type_}/{normalized_filename}.{extension}"
        
        # Set content type based on extension
        content_type = "application/pdf" if extension == "pdf" else "image/jpeg"
        
        # Add content disposition for PDFs
        extra_args = {
            "ContentType": content_type
        }
        
        if extension == "pdf":
            extra_args["ContentDisposition"] = f'attachment; filename="{normalized_filename}.{extension}"'
        
        # Process image if it's not a PDF
        if extension == "jpg" and type_ == "pictures":
            try:
                from PIL import Image
                
                # Resize image to max 600x600
                image = Image.open(io.BytesIO(file_data))
                image.thumbnail((600, 600))
                
                # Convert image to JPEG
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=80)
                file_data = output.getvalue()
            except ImportError:
                logger.warning("PIL not available, skipping image processing")
            except Exception as e:
                logger.error(f"Error processing image: {e}")
        
        try:
            # Upload the file
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=filepath,
                Body=file_data,
                **extra_args
            )
            
            # Return the URL
            return f"{settings.STORAGE_URL}/{filepath}"
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="There was an error while uploading the file."
            )

    def delete_object(self, user_id: Union[str, uuid.UUID], type_: str, filename: str) -> None:
        """
        Delete an object from storage.
        
        Args:
            user_id: User ID
            type_: Type of file ('pictures', 'previews', or 'resumes')
            filename: Filename to delete
        """
        if type_ not in ["pictures", "previews", "resumes"]:
            raise ValueError(f"Invalid file type: {type_}")
        
        extension = "pdf" if type_ == "resumes" else "jpg"
        
        # Construct the filepath
        filepath = f"{user_id}/{type_}/{filename}.{extension}"
        
        try:
            # Delete the file
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=filepath
            )
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"There was an error while deleting the document at the specified path: {filepath}."
            )

    def delete_folder(self, prefix: str) -> None:
        """
        Delete a folder and all its contents from storage.
        
        Args:
            prefix: Folder prefix (e.g., 'user_id/')
        """
        try:
            # List all objects in the folder
            objects_to_delete = []
            paginator = self.client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete the objects
            if objects_to_delete:
                self.client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )
                
            logger.info(f"Deleted {len(objects_to_delete)} objects from folder {prefix}")
        except Exception as e:
            logger.error(f"Error deleting folder: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"There was an error while deleting the folder at the specified path: {self.bucket_name}/{prefix}."
            )


# Singleton instance
storage_service = StorageService()