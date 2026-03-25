import pytest
from unittest.mock import Mock
from mcp.types import TextContent

import mcp_server

@pytest.fixture
def mock_client():
    client = Mock()
    return client

@pytest.mark.asyncio
async def test_handle_list_spaces(mock_client):
    mock_client.list_spaces.return_value = [
        {"name": "Space1", "slug": "space-1", "id": "uuid-1"}
    ]
    
    result = await mcp_server.handle_list_spaces(mock_client)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert "Space1" in result[0].text
    assert "space-1" in result[0].text
    assert "uuid-1" in result[0].text

@pytest.mark.asyncio
async def test_handle_list_spaces_empty(mock_client):
    mock_client.list_spaces.return_value = []
    
    result = await mcp_server.handle_list_spaces(mock_client)
    assert len(result) == 1
    assert "No spaces found" in result[0].text

@pytest.mark.asyncio
async def test_handle_search_docs(mock_client):
    mock_client.search.return_value = [
        {
            "title": "Welcome",
            "slugId": "slug-123",
            "space": {"name": "General"},
            "highlight": "This is a <b>test</b>"
        }
    ]
    
    result = await mcp_server.handle_search_docs(mock_client, query="test", space_id=None, max_results=5)
    text = result[0].text
    assert "Welcome" in text
    assert "slug-123" in text
    assert "General" in text
    assert "This is a **test**" in text

@pytest.mark.asyncio
async def test_handle_search_docs_empty(mock_client):
    mock_client.search.return_value = []
    result = await mcp_server.handle_search_docs(mock_client, query="test", space_id=None)
    assert "No results found" in result[0].text

@pytest.mark.asyncio
async def test_handle_get_page(mock_client):
    mock_client.get_page.return_value = {
        "title": "API Docs",
        "space": {"name": "Dev"},
        "creator": {"name": "Alice"},
        "updatedAt": "2026-03-22T00:00:00Z",
        "content": {"type": "doc", "content": []}
    }
    mock_client.prosemirror_to_markdown.return_value = "# API Docs Markdown"
    
    result = await mcp_server.handle_get_page(mock_client, "slug-123")
    text = result[0].text
    assert "API Docs" in text
    assert "Dev" in text
    assert "Alice" in text
    assert "2026-03-22" in text
    assert "# API Docs Markdown" in text

@pytest.mark.asyncio
async def test_handle_create_space(mock_client):
    mock_client.create_space.return_value = {
        "space": {"name": "New Space", "id": "uuid-1", "slug": "new-space"},
        "already_exists": False
    }
    
    result = await mcp_server.handle_create_space(mock_client, "New Space", "A desc")
    text = result[0].text
    assert "New Space" in text
    assert "uuid-1" in text

@pytest.mark.asyncio
async def test_handle_create_page(mock_client):
    mock_client.create_page.return_value = {
        "id": "page-1",
        "title": "Welcome",
        "spaceId": "space-1"
    }
    
    result = await mcp_server.handle_create_page(mock_client, "space-1", "Welcome", "# H", "parent-1")
    text = result[0].text
    assert "page-1" in text
    assert "Welcome" in text

@pytest.mark.asyncio
async def test_handle_update_page(mock_client):
    mock_client.update_page.return_value = {
        "id": "page-1",
        "title": "Updated",
        "updatedAt": "2026-03-22",
    }
    
    result = await mcp_server.handle_update_page(mock_client, "page-1", "Updated", "# H", "replace")
    text = result[0].text
    assert "page-1" in text
    assert "Updated" in text

@pytest.mark.asyncio
async def test_call_tool_dispatch():
    # Test that the dispatch is working and catches unknown tools
    import mcp_server
    
    # We patch get_client
    mock_client = Mock()
    mcp_server.get_client = Mock(return_value=mock_client)
    
    # Test valid tool
    mock_client.list_spaces.return_value = []
    result = await mcp_server.call_tool("list_spaces", {})
    assert "No spaces found" in result[0].text
    
    # Test invalid tool
    result = await mcp_server.call_tool("unknown_tool", {})
    assert "Unknown tool" in result[0].text
    
    # Test error
    mock_client.get_page.side_effect = Exception("API error")
    result = await mcp_server.call_tool("get_page", {"slug_id": "123"})
    assert "Error: API error" in result[0].text
