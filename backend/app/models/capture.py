"""
Capture model definitions.

Captures store the original input (text, audio, image) from users.
Used for traceability and duplicate detection.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ContentType


class CaptureBase(BaseModel):
    """Base capture fields."""

    content_type: ContentType = Field(..., description="コンテンツタイプ (TEXT/AUDIO/IMAGE)")
    content_url: Optional[str] = Field(
        None, max_length=500, description="Cloud Storage URL (AUDIO/IMAGEの場合)"
    )
    raw_text: Optional[str] = Field(
        None, max_length=10000, description="生テキスト (TEXTの場合)"
    )
    transcription: Optional[str] = Field(
        None, max_length=10000, description="文字起こし結果 (AUDIOの場合)"
    )
    image_analysis: Optional[str] = Field(
        None, max_length=5000, description="画像解析結果 (IMAGEの場合)"
    )


class CaptureCreate(CaptureBase):
    """Schema for creating a new capture."""

    base64_image: Optional[str] = Field(None, description="Base64 encoded image data (transient)")


class Capture(CaptureBase):
    """Complete capture model."""

    id: UUID
    user_id: str = Field(..., description="所有者ユーザーID")
    processed: bool = Field(False, description="タスク化処理済みか")
    created_at: datetime

    class Config:
        from_attributes = True

    @property
    def text_content(self) -> str:
        """Get the text content regardless of content type."""
        if self.content_type == ContentType.TEXT:
            return self.raw_text or ""
        elif self.content_type == ContentType.AUDIO:
            return self.transcription or ""
        elif self.content_type == ContentType.IMAGE:
            return self.image_analysis or ""
        return ""
