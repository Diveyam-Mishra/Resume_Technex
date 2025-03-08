# app/services/storage.py
import logging
import os
import shutil
import uuid
from typing import Optional, Union
from fastapi import HTTPException, status
from pathlib import Path

from app.config.settings import settings
from app.utils.constants import ErrorMessage

logger = logging.getLogger(__name__)

class StorageService:
    """
    Service for handling storage operations with local filesystem.
    """
    def _init_(self):
        """
        Initialize the storage service.
        """
        self.storage_dir = settings.LOCAL_STORAGE_PATH
        self._initialize_storage()

    def _initialize_storage(self):
        """
        Initialize the storage directories.
        """
        try:
            # Create base directory if it doesn't exist
            os.makedirs(self.storage_dir, exist_ok=True)
            
            # Create subdirectories for different types
            for folder in ['pictures', 'previews', 'resumes']:
                os.makedirs(os.path.join(self.storage_dir, folder), exist_ok=True)
                
            logger.info(f"Storage directories created at {self.storage_dir}")
        except Exception as e:
            logger.error(f"Error initializing storage: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="There was an error while initializing the storage service."
            )

    def bucket_exists(self) -> bool:
        """
        Check if the storage directory exists.
        """
        return os.path.exists(self.storage_dir)

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
        
        # Generate a unique filename if not provided
        if not filename:
            filename = str(uuid.uuid4())
        
        # Sanitize filename - remove any path components
        safe_filename = os.path.basename(filename)
        
        # Ensure user directory exists
        user_dir = os.path.join(self.storage_dir, str(user_id), type_)
        os.makedirs(user_dir, exist_ok=True)
        
        # Complete filepath
        filepath = os.path.join(user_dir, f"{safe_filename}.{extension}")
        
        try:
            # Write the file
            with open(filepath, 'wb') as f:
                f.write(file_data)
            
            # Return URL to access the file
            return f"{settings.PUBLIC_URL}/storage/{str(user_id)}/{type_}/{safe_filename}.{extension}"
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
        
        # Complete filepath
        filepath = os.path.join(self.storage_dir, str(user_id), type_, f"{filename}.{extension}")
        
        try:
            # Delete the file if it exists
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"There was an error while deleting the file: {filepath}"
            )

    def delete_folder(self, prefix: str) -> None:
        """
        Delete a folder and all its contents from storage.
        
        Args:
            prefix: Folder path (e.g., 'user_id/')
        """
        folder_path = os.path.join(self.storage_dir, prefix)
        
        try:
            # Delete the folder and all its contents if it exists
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)
        except Exception as e:
            logger.error(f"Error deleting folder: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"There was an error while deleting the folder: {folder_path}"
            )


# Singleton instance
storage_service = StorageService()