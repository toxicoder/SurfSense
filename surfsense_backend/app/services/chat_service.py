from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db import (
    NewChatMessage,
    NewChatMessageRole,
    NewChatThread,
    Permission,
    User,
)
from app.schemas.new_chat import (
    NewChatThreadCreate,
    NewChatThreadUpdate,
)
from app.utils.rbac import check_permission


class ChatService:
    def __init__(self, session: AsyncSession, user: User):
        self.session = session
        self.user = user

    async def list_threads(self, search_space_id: int, limit: int | None = None) -> tuple[list[NewChatThread], list[NewChatThread]]:
        """
        List all threads for the current user in a search space.
        Returns tuple of (active_threads, archived_threads).
        Optimized to use database-level filtering.
        """
        await check_permission(
            self.session,
            self.user,
            search_space_id,
            Permission.CHATS_READ.value,
            "You don't have permission to read chats in this search space",
        )

        # Query for active threads
        query_active = (
            select(NewChatThread)
            .filter(
                NewChatThread.search_space_id == search_space_id,
                NewChatThread.archived == False  # noqa: E712
            )
            .order_by(NewChatThread.updated_at.desc())
        )
        if limit is not None and limit > 0:
            query_active = query_active.limit(limit)

        # Query for archived threads
        query_archived = (
            select(NewChatThread)
            .filter(
                NewChatThread.search_space_id == search_space_id,
                NewChatThread.archived == True  # noqa: E712
            )
            .order_by(NewChatThread.updated_at.desc())
        )

        try:
            result_active = await self.session.execute(query_active)
            result_archived = await self.session.execute(query_archived)
            return result_active.scalars().all(), result_archived.scalars().all()
        except OperationalError as e:
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def search_threads(self, search_space_id: int, title: str) -> list[NewChatThread]:
        await check_permission(
            self.session,
            self.user,
            search_space_id,
            Permission.CHATS_READ.value,
            "You don't have permission to read chats in this search space",
        )

        query = (
            select(NewChatThread)
            .filter(
                NewChatThread.search_space_id == search_space_id,
                NewChatThread.title.ilike(f"%{title}%"),
            )
            .order_by(NewChatThread.updated_at.desc())
        )

        try:
            result = await self.session.execute(query)
            return result.scalars().all()
        except OperationalError as e:
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def verify_thread_access(self, thread_id: int, search_space_id: int) -> NewChatThread:
        """
        Verify that a thread exists and belongs to the specified search space.
        """
        try:
            result = await self.session.execute(
                select(NewChatThread).filter(NewChatThread.id == thread_id)
            )
            thread = result.scalars().first()

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            if thread.search_space_id != search_space_id:
                raise HTTPException(
                    status_code=403,
                    detail="Thread does not belong to the specified search space",
                )

            return thread
        except OperationalError as e:
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def create_thread(self, thread_data: NewChatThreadCreate) -> NewChatThread:
        await check_permission(
            self.session,
            self.user,
            thread_data.search_space_id,
            Permission.CHATS_CREATE.value,
            "You don't have permission to create chats in this search space",
        )

        now = datetime.now(UTC)
        db_thread = NewChatThread(
            title=thread_data.title,
            archived=thread_data.archived,
            search_space_id=thread_data.search_space_id,
            updated_at=now,
        )
        self.session.add(db_thread)
        try:
            await self.session.commit()
            await self.session.refresh(db_thread)
            return db_thread
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=400,
                detail="Database constraint violation. Please check your input data.",
            ) from None
        except OperationalError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def get_thread_with_messages(self, thread_id: int) -> NewChatThread:
        try:
            result = await self.session.execute(
                select(NewChatThread)
                .options(selectinload(NewChatThread.messages))
                .filter(NewChatThread.id == thread_id)
            )
            thread = result.scalars().first()

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            await check_permission(
                self.session,
                self.user,
                thread.search_space_id,
                Permission.CHATS_READ.value,
                "You don't have permission to read chats in this search space",
            )

            return thread
        except OperationalError as e:
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def update_thread(self, thread_id: int, thread_update: NewChatThreadUpdate) -> NewChatThread:
        try:
            result = await self.session.execute(
                select(NewChatThread).filter(NewChatThread.id == thread_id)
            )
            db_thread = result.scalars().first()

            if not db_thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            await check_permission(
                self.session,
                self.user,
                db_thread.search_space_id,
                Permission.CHATS_UPDATE.value,
                "You don't have permission to update chats in this search space",
            )

            update_data = thread_update.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_thread, key, value)

            db_thread.updated_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(db_thread)
            return db_thread
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=400,
                detail="Database constraint violation. Please check your input data.",
            ) from None
        except OperationalError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def delete_thread(self, thread_id: int) -> bool:
        try:
            result = await self.session.execute(
                select(NewChatThread).filter(NewChatThread.id == thread_id)
            )
            db_thread = result.scalars().first()

            if not db_thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            await check_permission(
                self.session,
                self.user,
                db_thread.search_space_id,
                Permission.CHATS_DELETE.value,
                "You don't have permission to delete chats in this search space",
            )

            await self.session.delete(db_thread)
            await self.session.commit()
            return True
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=400, detail="Cannot delete thread due to existing dependencies."
            ) from None
        except OperationalError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    async def append_message(self, thread_id: int, role: str, content: Any) -> NewChatMessage:
        try:
            # Get thread
            result = await self.session.execute(
                select(NewChatThread).filter(NewChatThread.id == thread_id)
            )
            thread = result.scalars().first()

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            await check_permission(
                self.session,
                self.user,
                thread.search_space_id,
                Permission.CHATS_UPDATE.value,
                "You don't have permission to update chats in this search space",
            )

            # Convert role
            role_str = role.lower() if isinstance(role, str) else role
            try:
                message_role = NewChatMessageRole(role_str)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {role}. Must be 'user', 'assistant', or 'system'.",
                ) from None

            # Create message
            db_message = NewChatMessage(
                thread_id=thread_id,
                role=message_role,
                content=content,
            )
            self.session.add(db_message)

            # Update thread's updated_at timestamp
            thread.updated_at = datetime.now(UTC)

            # Auto-generate title logic
            if thread.title == "New Chat" and role_str == "user":
                self._update_thread_title(thread, content)

            await self.session.commit()
            await self.session.refresh(db_message)
            return db_message
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=400,
                detail="Database constraint violation. Please check your input data.",
            ) from None
        except OperationalError as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e

    def _update_thread_title(self, thread: NewChatThread, content: Any):
        title_text = ""
        if isinstance(content, str):
            title_text = content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    title_text = part.get("text", "")
                    break
                elif isinstance(part, str):
                    title_text = part
                    break
        else:
            title_text = str(content)

        if title_text:
            thread.title = title_text[:100] + (
                "..." if len(title_text) > 100 else ""
            )

    async def list_messages(self, thread_id: int, skip: int = 0, limit: int = 100) -> list[NewChatMessage]:
        try:
            # Verify thread exists and user has access
            result = await self.session.execute(
                select(NewChatThread).filter(NewChatThread.id == thread_id)
            )
            thread = result.scalars().first()

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            await check_permission(
                self.session,
                self.user,
                thread.search_space_id,
                Permission.CHATS_READ.value,
                "You don't have permission to read chats in this search space",
            )

            query = (
                select(NewChatMessage)
                .filter(NewChatMessage.thread_id == thread_id)
                .order_by(NewChatMessage.created_at)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return result.scalars().all()
        except OperationalError as e:
            raise HTTPException(
                status_code=503, detail="Database operation failed. Please try again later."
            ) from e
