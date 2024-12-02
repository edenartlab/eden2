import pytest
import json
from unittest.mock import AsyncMock, patch
from eve.sdk.eden.client import EdenClient, EdenApiUrls
from pydantic import SecretStr


@pytest.fixture
def mock_api_urls():
    return EdenApiUrls(
        api_url="https://mock-api.eden.art",
        tools_api_url="https://mock-tools.eden.art",
    )


@pytest.fixture
def mock_client(mock_api_urls):
    with patch("eve.sdk.eden.client.get_api_key") as mock_get_key:
        mock_get_key.return_value = SecretStr("mock-api-key")
        client = EdenClient(api_urls=mock_api_urls)
        return client


@pytest.mark.asyncio
async def test_async_chat(mock_client):
    chat_updates = [
        {"type": "ASSISTANT_MESSAGE", "content": "Hello!"},
        {"type": "TOOL_COMPLETE", "tool": "test_tool", "result": {"data": "test"}},
    ]

    async def mock_stream_response():
        for update in chat_updates:
            yield f"data: {json.dumps({'event': 'update', 'data': update})}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'data': ''})}\n\n"

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.aiter_lines = mock_stream_response
        mock_post.return_value = mock_response

        updates = []
        async for update in mock_client.async_chat(
            user_message="Hello", thread_name="test_thread"
        ):
            updates.append(update)

        assert len(updates) == 2
        assert updates[0]["type"] == "ASSISTANT_MESSAGE"
        assert updates[1]["type"] == "TOOL_COMPLETE"


def test_sync_chat(mock_client):
    chat_updates = [
        {"type": "ASSISTANT_MESSAGE", "content": "Hello!"},
        {"type": "TOOL_COMPLETE", "tool": "test_tool", "result": {"data": "test"}},
    ]

    async def mock_async_chat(*args, **kwargs):
        for update in chat_updates:
            yield update

    with patch.object(mock_client, "async_chat", side_effect=mock_async_chat):
        updates = mock_client.chat(user_message="Hello", thread_name="test_thread")

        assert len(updates) == 2
        assert updates[0]["type"] == "ASSISTANT_MESSAGE"
        assert updates[1]["type"] == "TOOL_COMPLETE"


@pytest.mark.asyncio
async def test_subscribe_events(mock_client):
    events = [
        {"status": "processing", "progress": 0.5},
        {"status": "completed", "result": {"data": "test"}},
    ]

    async def mock_stream_response():
        for event in events:
            yield f"event: task-update\n"
            yield f"data: {json.dumps(event)}\n\n"

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_context = AsyncMock()
        mock_context.aiter_lines = mock_stream_response
        mock_stream.return_value.__aenter__.return_value = mock_context

        received_events = []
        async for event in mock_client._subscribe("mock_task_id"):
            received_events.append(event)

        assert len(received_events) == 2
        assert received_events[0]["status"] == "processing"
        assert received_events[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_http_error_handling(mock_client):
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            await mock_client.async_create(
                workflow="txt2img", args={"prompt": "test prompt"}
            )
