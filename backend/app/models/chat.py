"""
Chat model definitions.

Models for the main chat interface between user and secretary agent.
"""

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ChatMode


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    text: Optional[str] = Field(None, max_length=10000, description="テキスト入力")
    audio_url: Optional[str] = Field(None, description="音声ファイルURL")
    image_url: Optional[str] = Field(None, description="画像ファイルURL")
    image_base64: Optional[str] = Field(None, description="Base64エンコードされた画像データ（data:image/...形式）")
    mode: ChatMode = Field(ChatMode.DUMP, description="チャットモード")
    session_id: Optional[str] = Field(None, description="セッションID（継続会話用）")
    context: dict[str, Any] = Field(default_factory=dict, description="追加コンテキスト")


class SuggestedAction(BaseModel):
    """Suggested action for the user."""

    action_type: str = Field(..., description="アクションタイプ")
    label: str = Field(..., description="表示ラベル")
    payload: dict[str, Any] = Field(default_factory=dict, description="アクション実行用データ")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    assistant_message: str = Field(..., description="アシスタントの応答メッセージ")
    related_tasks: list[UUID] = Field(
        default_factory=list, description="関連するタスクIDリスト"
    )
    suggested_actions: list[SuggestedAction] = Field(
        default_factory=list, description="提案アクションリスト"
    )
    session_id: str = Field(..., description="セッションID")
    capture_id: Optional[UUID] = Field(None, description="作成されたCaptureのID")


class StreamingChatChunk(BaseModel):
    """Streaming chat response chunk."""

    chunk_type: str = Field(..., description="チャンクタイプ (text/tool_call/done)")
    content: str = Field("", description="テキストコンテンツ")
    tool_name: Optional[str] = Field(None, description="ツール名（tool_callの場合）")
    tool_result: Optional[dict[str, Any]] = Field(None, description="ツール実行結果")
