import pytest
from unittest.mock import patch, AsyncMock

from eve.sdk.eden.client import EdenClient, EdenApiUrls, SecretStr


@pytest.fixture
def local_urls():
    return EdenApiUrls(
        api_url="http://localhost:5050", tools_api_url="http://localhost:8000"
    )


@pytest.fixture
def mock_api_key():
    with patch("eve.eve.sdk.eden.client.get_api_key") as mock:
        mock.return_value = SecretStr("test-api-key")
        yield mock


@pytest.fixture
def eden_client(local_urls, mock_api_key):
    return EdenClient(api_urls=local_urls)


@pytest.mark.asyncio
async def test_async_create(eden_client):
    workflow = "test-workflow"
    args = {"param": "value"}

    # Mock the HTTP response for task creation
    task_response = {"task": {"_id": "test-task-id"}}
    completion_event = {"status": "completed", "result": {"output": "success"}}

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post.return_value.json.return_value = task_response

        # Mock the _subscribe method
        with patch.object(
            eden_client, "_subscribe", new_callable=AsyncMock
        ) as mock_subscribe:
            mock_subscribe.return_value.__aiter__.return_value = [completion_event]

            result = await eden_client.async_create(workflow, args)

            assert result == {"output": "success"}

            # Verify the API was called with correct parameters
            mock_client.return_value.__aenter__.return_value.post.assert_called_once()
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args[0][0] == "http://localhost:5050/v2/tasks/create"


@pytest.mark.asyncio
async def test_async_chat(eden_client):
    message = "Hello"
    thread_id = "test-thread"
    agent_id = "test-agent"

    chat_responses = [
        {"role": "assistant", "content": "Hi there!"},
        {"role": "assistant", "content": "How can I help?"},
    ]

    with patch.object(eden_client, "async_run_ws", new_callable=AsyncMock) as mock_ws:
        mock_ws.return_value.__aiter__.return_value = chat_responses

        responses = [
            msg async for msg in eden_client.async_chat(message, thread_id, agent_id)
        ]

        assert responses == chat_responses
        mock_ws.assert_called_once_with(
            "/ws/chat",
            {"message": message, "thread_id": thread_id, "agent_id": agent_id},
        )


def test_get_or_create_thread(eden_client):
    thread_name = "test-thread"
    expected_thread_id = "123"

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value.json.return_value = {
            "thread_id": expected_thread_id
        }

        thread_id = eden_client.get_or_create_thread(thread_name)

        assert thread_id == expected_thread_id
        mock_client.return_value.__enter__.return_value.post.assert_called_once_with(
            "http://localhost:8000/thread/create",
            headers={"X-Api-Key": "test-api-key"},
            json={"name": thread_name},
        )


@pytest.mark.asyncio
async def test_async_upload(eden_client, tmp_path):
    # Create a temporary test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    expected_response = {"url": "http://example.com/media/123"}

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post.return_value.json.return_value = expected_response

        result = await eden_client.async_upload(str(test_file))

        assert result == expected_response
        mock_client.return_value.__aenter__.return_value.post.assert_called_once()
        assert (
            mock_client.return_value.__aenter__.return_value.post.call_args[0][0]
            == "http://localhost:5050/media/upload"
        )


def test_get_discord_channels(eden_client):
    expected_channels = [{"id": "123", "name": "general"}]

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value.json.return_value = expected_channels

        channels = eden_client.get_discord_channels()

        assert channels == expected_channels
        mock_client.return_value.__enter__.return_value.post.assert_called_once_with(
            "http://localhost:8000/chat/discord/channels",
            headers={"X-Api-Key": "test-api-key"},
            json={},
        )
