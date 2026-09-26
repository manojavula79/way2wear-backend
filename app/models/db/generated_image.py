"""
BACKEND TASK B - PART 3: Database Model

Location: app/models/db/generated_image.py

Add this model to your project to store generated images metadata.
"""

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid


class GeneratedImage(Base):
    """
    Model to store generated outfit images metadata.
    
    Fields:
    - id: Unique image ID (UUID)
    - user_id: User who generated the image
    - outfit_description: Outfit text (e.g., "white kurti + blue palazzo")
    - temporary_url: Original DALL-E URL (expires in 1 hour)
    - permanent_url: S3/cloud storage URL (permanent)
    - storage_path: Path in cloud storage
    - prompt_used: The full prompt sent to DALL-E
    - user_edit: User's refinement/edit if any
    - style_hint: Photography style used
    - user_context: User demographics (gender, skin tone, etc)
    - file_size: Image file size in bytes
    - image_width: Image width in pixels
    - image_height: Image height in pixels
    - created_at: Creation timestamp
    - updated_at: Last update timestamp
    - status: Generation status (pending, downloaded, stored, failed)
    - error_message: Error message if generation failed
    """
    
    __tablename__ = "generated_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Outfit info
    outfit_description = Column(String(500), nullable=False)
    
    # URLs
    temporary_url = Column(String(1000))  # DALL-E URL (expires in 1 hour)
    permanent_url = Column(String(1000))  # S3/storage permanent URL
    storage_path = Column(String(500))    # Path in cloud storage
    
    # Generation info
    prompt_used = Column(String(1000))    # Full prompt sent to DALL-E
    user_edit = Column(String(500))       # User's refinement/edit if any
    style_hint = Column(String(200))      # Photography style hint
    user_context = Column(String(300))    # User demographics
    
    # Image metadata
    file_size = Column(Integer)           # File size in bytes
    image_width = Column(Integer)         # Image width in pixels
    image_height = Column(Integer)        # Image height in pixels
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Status
    status = Column(String(50), default="pending")  # pending, downloaded, stored, failed
    error_message = Column(String(500))


# SQL Migration for Supabase
"""
CREATE TABLE generated_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    outfit_description VARCHAR(500) NOT NULL,
    
    temporary_url VARCHAR(1000),
    permanent_url VARCHAR(1000),
    storage_path VARCHAR(500),
    
    prompt_used VARCHAR(1000),
    user_edit VARCHAR(500),
    style_hint VARCHAR(200),
    user_context VARCHAR(300),
    
    file_size INTEGER,
    image_width INTEGER,
    image_height INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    status VARCHAR(50) DEFAULT 'pending',
    error_message VARCHAR(500),
    
    CREATED INDEX idx_generated_images_user_id ON generated_images(user_id),
    CREATED INDEX idx_generated_images_created_at ON generated_images(created_at)
);
"""
