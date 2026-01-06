"""
Routes for the new chat feature with assistant-ui integration.

These endpoints support the ThreadHistoryAdapter pattern from assistant-ui:
- GET /threads - List threads for sidebar (ThreadListPrimitive)
- POST /threads - Create a new thread
- GET /threads/{thread_id} - Get thread with messages (load)
- PUT /threads/{thread_id} - Update thread (rename, archive)
- DELETE /threads/{thread_id} - Delete thread
- POST /threads/{thread_id}/messages - Append message
- POST /attachments/process - Process attachments for chat context
"""

import contextlib
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import (
    Permission,
    SearchSpace,
    User,
    get_async_session,
)
from app.schemas.new_chat import (
    NewChatMessageRead,
    NewChatRequest,
    NewChatThreadCreate,
    NewChatThreadRead,
    NewChatThreadUpdate,
    NewChatThreadWithMessages,
    ThreadHistoryLoadResponse,
    ThreadListItem,
    ThreadListResponse,
)
from app.services.chat_service import ChatService
from app.tasks.chat.stream_new_chat import stream_new_chat
from app.users import current_active_user
from app.utils.rbac import check_permission

router = APIRouter()


# =============================================================================
# Thread Endpoints
# =============================================================================


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    search_space_id: int,
    limit: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    List all threads for the current user in a search space.
    Returns threads and archived_threads for ThreadListPrimitive.

    Args:
        search_space_id: The search space to list threads for
        limit: Optional limit on number of threads to return (applies to active threads only)

    Requires CHATS_READ permission.
    """
    service = ChatService(session, user)
    active_threads, archived_threads_db = await service.list_threads(search_space_id, limit)

    # Convert to schema
    threads = [
        ThreadListItem(
            id=thread.id,
            title=thread.title,
            archived=thread.archived,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        for thread in active_threads
    ]

    archived_threads = [
        ThreadListItem(
            id=thread.id,
            title=thread.title,
            archived=thread.archived,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        for thread in archived_threads_db
    ]

    return ThreadListResponse(threads=threads, archived_threads=archived_threads)


@router.get("/threads/search", response_model=list[ThreadListItem])
async def search_threads(
    search_space_id: int,
    title: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Search threads by title in a search space.

    Args:
        search_space_id: The search space to search in
        title: The search query (case-insensitive partial match)

    Requires CHATS_READ permission.
    """
    service = ChatService(session, user)
    threads = await service.search_threads(search_space_id, title)

    return [
        ThreadListItem(
            id=thread.id,
            title=thread.title,
            archived=thread.archived,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        for thread in threads
    ]


@router.post("/threads", response_model=NewChatThreadRead)
async def create_thread(
    thread: NewChatThreadCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Create a new chat thread.

    Requires CHATS_CREATE permission.
    """
    service = ChatService(session, user)
    return await service.create_thread(thread)


@router.get("/threads/{thread_id}", response_model=ThreadHistoryLoadResponse)
async def get_thread_messages(
    thread_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Get a thread with all its messages.
    This is used by ThreadHistoryAdapter.load() to restore conversation.

    Requires CHATS_READ permission.
    """
    service = ChatService(session, user)
    thread = await service.get_thread_with_messages(thread_id)

    # Return messages in the format expected by assistant-ui
    messages = [
        NewChatMessageRead(
            id=msg.id,
            thread_id=msg.thread_id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg in thread.messages
    ]

    return ThreadHistoryLoadResponse(messages=messages)


@router.get("/threads/{thread_id}/full", response_model=NewChatThreadWithMessages)
async def get_thread_full(
    thread_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Get full thread details with all messages.

    Requires CHATS_READ permission.
    """
    service = ChatService(session, user)
    return await service.get_thread_with_messages(thread_id)


@router.put("/threads/{thread_id}", response_model=NewChatThreadRead)
async def update_thread(
    thread_id: int,
    thread_update: NewChatThreadUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Update a thread (title, archived status).
    Used for renaming and archiving threads.

    Requires CHATS_UPDATE permission.
    """
    service = ChatService(session, user)
    return await service.update_thread(thread_id, thread_update)


@router.delete("/threads/{thread_id}", response_model=dict)
async def delete_thread(
    thread_id: int,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Delete a thread and all its messages.

    Requires CHATS_DELETE permission.
    """
    service = ChatService(session, user)
    await service.delete_thread(thread_id)
    return {"message": "Thread deleted successfully"}


# =============================================================================
# Message Endpoints
# =============================================================================


@router.post("/threads/{thread_id}/messages", response_model=NewChatMessageRead)
async def append_message(
    thread_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Append a message to a thread.
    This is used by ThreadHistoryAdapter.append() to persist messages.

    Requires CHATS_UPDATE permission.
    """
    # Parse raw body - extract only role and content, ignoring extra fields
    raw_body = await request.json()
    role = raw_body.get("role")
    content = raw_body.get("content")

    if not role:
        raise HTTPException(status_code=400, detail="Missing required field: role")
    if content is None:
        raise HTTPException(
            status_code=400, detail="Missing required field: content"
        )

    service = ChatService(session, user)
    return await service.append_message(thread_id, role, content)


@router.get("/threads/{thread_id}/messages", response_model=list[NewChatMessageRead])
async def list_messages(
    thread_id: int,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    List messages in a thread with pagination.

    Requires CHATS_READ permission.
    """
    service = ChatService(session, user)
    return await service.list_messages(thread_id, skip, limit)


# =============================================================================
# Chat Streaming Endpoint
# =============================================================================


@router.post("/new_chat")
async def handle_new_chat(
    request: NewChatRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Stream chat responses from the deep agent.

    This endpoint handles the new chat functionality with streaming responses
    using Server-Sent Events (SSE) format compatible with Vercel AI SDK.

    Requires CHATS_CREATE permission.
    """
    try:
        # Use ChatService just to verify access (optional, but good practice)
        # However, stream_new_chat task might do its own checks or rely on the caller?
        # The original code checked permission explicitly.

        # We can use a lightweight service method or just keep the check here.
        # Keeping it here is fine as it's "controller" logic for this endpoint.

        # Verify thread exists and user has permission
        # Note: ChatService doesn't have a simple "check_permission" public method yet.
        # We can implement one or just use check_permission util directly.
        # Let's use check_permission directly to avoid overhead of fetching full thread if not needed,
        # but we need the thread object anyway.

        service = ChatService(session, user)
        # This will fetch thread and check READ/UPDATE permissions?
        # Actually handle_new_chat requires CHATS_CREATE (weird, maybe CHATS_UPDATE?)
        # Original code: CHATS_CREATE.

        # We can just fetch the thread using service (which checks READ) and then check CREATE?
        # Or just stick to original logic here since it involves SearchSpace config too.

        # Verify thread access first (IDOR fix)
        service = ChatService(session, user)
        # Only verify if chat_id exists and is not 0/new
        if request.chat_id and request.chat_id > 0:
            await service.verify_thread_access(request.chat_id, request.search_space_id)

        # Original Logic:
        result = await session.execute(
            select(SearchSpace).filter(SearchSpace.id == request.search_space_id)
        )
        search_space = result.scalars().first()

        if not search_space:
            raise HTTPException(status_code=404, detail="Search space not found")

        await check_permission(
            session,
            user,
            request.search_space_id,
            Permission.CHATS_CREATE.value,
            "You don't have permission to chat in this search space",
        )

        # Use agent_llm_id from search space for chat operations
        llm_config_id = (
            search_space.agent_llm_id if search_space.agent_llm_id is not None else -1
        )

        # Return streaming response
        return StreamingResponse(
            stream_new_chat(
                user_query=request.user_query,
                search_space_id=request.search_space_id,
                chat_id=request.chat_id,
                session=session,
                llm_config_id=llm_config_id,
                attachments=request.attachments,
                mentioned_document_ids=request.mentioned_document_ids,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {e!s}",
        ) from None


# =============================================================================
# Attachment Processing Endpoint
# =============================================================================


@router.post("/attachments/process")
async def process_attachment(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Process an attachment file and extract its content as markdown.

    This endpoint uses the configured ETL service to parse files and return
    the extracted content that can be used as context in chat messages.

    Supported file types depend on the configured ETL_SERVICE:
    - Markdown/Text files: .md, .markdown, .txt (always supported)
    - Audio files: .mp3, .mp4, .mpeg, .mpga, .m4a, .wav, .webm (if STT configured)
    - Documents: .pdf, .docx, .doc, .pptx, .xlsx (depends on ETL service)

    Returns:
        JSON with attachment id, name, type, and extracted content
    """
    from app.config import config as app_config

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    filename = file.filename
    attachment_id = str(uuid.uuid4())

    try:
        # Save file to a temporary location
        file_ext = os.path.splitext(filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_path = temp_file.name
            content = await file.read()
            temp_file.write(content)

        extracted_content = ""

        # Process based on file type
        if file_ext in (".md", ".markdown", ".txt"):
            # For text/markdown files, read content directly
            with open(temp_path, encoding="utf-8") as f:
                extracted_content = f.read()

        elif file_ext in (".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"):
            # Audio files - transcribe if STT service is configured
            if not app_config.STT_SERVICE:
                raise HTTPException(
                    status_code=422,
                    detail="Audio transcription is not configured. Please set STT_SERVICE.",
                )

            stt_service_type = (
                "local" if app_config.STT_SERVICE.startswith("local/") else "external"
            )

            if stt_service_type == "local":
                from app.services.stt_service import stt_service

                result = stt_service.transcribe_file(temp_path)
                extracted_content = result.get("text", "")
            else:
                from litellm import atranscription

                with open(temp_path, "rb") as audio_file:
                    transcription_kwargs = {
                        "model": app_config.STT_SERVICE,
                        "file": audio_file,
                        "api_key": app_config.STT_SERVICE_API_KEY,
                    }
                    if app_config.STT_SERVICE_API_BASE:
                        transcription_kwargs["api_base"] = (
                            app_config.STT_SERVICE_API_BASE
                        )

                    transcription_response = await atranscription(
                        **transcription_kwargs
                    )
                    extracted_content = transcription_response.get("text", "")

            if extracted_content:
                extracted_content = (
                    f"# Transcription of {filename}\n\n{extracted_content}"
                )

        else:
            # Document files - use configured ETL service
            if app_config.ETL_SERVICE == "UNSTRUCTURED":
                from langchain_unstructured import UnstructuredLoader

                from app.utils.document_converters import convert_document_to_markdown

                loader = UnstructuredLoader(
                    temp_path,
                    mode="elements",
                    post_processors=[],
                    languages=["eng"],
                    include_orig_elements=False,
                    include_metadata=False,
                    strategy="auto",
                )
                docs = await loader.aload()
                extracted_content = await convert_document_to_markdown(docs)

            elif app_config.ETL_SERVICE == "LLAMACLOUD":
                from llama_cloud_services import LlamaParse
                from llama_cloud_services.parse.utils import ResultType

                parser = LlamaParse(
                    api_key=app_config.LLAMA_CLOUD_API_KEY,
                    num_workers=1,
                    verbose=False,
                    language="en",
                    result_type=ResultType.MD,
                )
                result = await parser.aparse(temp_path)
                markdown_documents = await result.aget_markdown_documents(
                    split_by_page=False
                )

                if markdown_documents:
                    extracted_content = "\n\n".join(
                        doc.text for doc in markdown_documents
                    )

            elif app_config.ETL_SERVICE == "DOCLING":
                from app.services.docling_service import create_docling_service

                docling_service = create_docling_service()
                result = await docling_service.process_document(temp_path, filename)
                extracted_content = result.get("content", "")

            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"ETL service not configured or unsupported file type: {file_ext}",
                )

        # Clean up temp file
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        if not extracted_content:
            raise HTTPException(
                status_code=422,
                detail=f"Could not extract content from file: {filename}",
            )

        # Determine attachment type (must be one of: "image", "document", "file")
        # assistant-ui only supports these three types
        if file_ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            attachment_type = "image"
        else:
            # All other files (including audio, documents, text) are treated as "document"
            attachment_type = "document"

        return {
            "id": attachment_id,
            "name": filename,
            "type": attachment_type,
            "content": extracted_content,
            "contentLength": len(extracted_content),
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp file on error
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        raise HTTPException(
            status_code=500,
            detail=f"Failed to process attachment: {e!s}",
        ) from e
