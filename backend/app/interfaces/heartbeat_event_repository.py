from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.models.heartbeat import HeartbeatEvent, HeartbeatEventCreate


class IHeartbeatEventRepository(ABC):
    @abstractmethod
    async def create(self, event: HeartbeatEventCreate) -> HeartbeatEvent:
        pass

    @abstractmethod
    async def list_by_user_since(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[HeartbeatEvent]:
        pass

    @abstractmethod
    async def count_by_user_since(self, user_id: str, since: Optional[datetime] = None) -> int:
        pass

    @abstractmethod
    async def get_latest_for_task(self, user_id: str, task_id: UUID) -> Optional[HeartbeatEvent]:
        pass

    @abstractmethod
    async def count_unread(self, user_id: str) -> int:
        pass

    @abstractmethod
    async def list_unread(self, user_id: str) -> list[HeartbeatEvent]:
        pass

    @abstractmethod
    async def mark_all_read(self, user_id: str) -> int:
        pass
