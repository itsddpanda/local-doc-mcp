import pytest
import responses
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, mock_open

from docmost_client import DocmostClient

# We use the fixture mock_client from conftest.py
# Let's test the client methods

@responses.activate
def test_login_success(mock_client, mock_config):
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/auth/login",
        json={"success": True},
        status=200,
        headers={"Set-Cookie": "authToken=new-jwt-token; Path=/; HttpOnly"}
    )
    
    token = mock_client.login()
    assert token == "new-jwt-token"
    assert mock_client.token == "new-jwt-token"

@responses.activate
def test_login_failure(mock_client, mock_config):
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/auth/login",
        status=401,
        json={"error": "Unauthorized"}
    )
    
    with pytest.raises(Exception):
        mock_client.login()

def test_is_token_expired_true():
    client = DocmostClient()
    # Mocking ancient token
    client.token_created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    assert client._is_token_expired() is True

def test_is_token_expired_false():
    client = DocmostClient()
    # Fresh token
    client.token_created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert client._is_token_expired() is False

@responses.activate
def test_request_raw_with_retry(mock_client, mock_config):
    # First request fails with 401
    responses.add(
        responses.GET,
        f"{mock_config['base_url']}/api/test",
        status=401
    )
    # Login is called to refresh token
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/auth/login",
        status=200,
        headers={"Set-Cookie": "authToken=refreshed-token; Path=/; HttpOnly"}
    )
    # Second request succeeds
    responses.add(
        responses.GET,
        f"{mock_config['base_url']}/api/test",
        status=200,
        json={"success": True}
    )
    
    resp = mock_client._request_raw("GET", "/api/test")
    assert resp.status_code == 200
    assert mock_client.token == "refreshed-token"

@responses.activate
def test_list_spaces(mock_client, mock_config):
    spaces_data = {
        "success": True,
        "data": {
            "items": [
                {"id": "space1", "name": "Engineering"},
                {"id": "space2", "name": "Marketing"}
            ]
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/spaces",
        status=200,
        json=spaces_data
    )
    
    result = mock_client.list_spaces(1, 100)
    assert len(result) == 2
    assert result[0]["name"] == "Engineering"

@responses.activate
def test_search_docs(mock_client, mock_config):
    search_data = {
        "success": True,
        "data": {
            "items": [
                {"id": "doc1", "title": "API Spec"}
            ]
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/search",
        status=200,
        json=search_data
    )
    
    result = mock_client.search("API", space_id="space1")
    assert len(result) == 1
    assert result[0]["title"] == "API Spec"
    
    # Assert correct payload was sent
    req = responses.calls[0].request
    parsed_payload = json.loads(req.body)
    assert parsed_payload["query"] == "API"
    assert parsed_payload["spaceId"] == "space1"

@responses.activate
def test_get_page(mock_client, mock_config):
    page_data = {
        "success": True,
        "data": {
            "title": "API Spec",
            "content": {"type": "doc", "content": []}
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/info",
        status=200,
        json=page_data
    )
    
    result = mock_client.get_page("page_slug_123")
    assert result["title"] == "API Spec"

@responses.activate
def test_create_space(mock_client, mock_config):
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/spaces",
        status=200,
        json={"data": {"items": []}}
    )
    create_data = {
        "success": True,
        "data": {
            "id": "new-space",
            "name": "New Space"
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/spaces/create",
        status=200,
        json=create_data
    )
    
    result = mock_client.create_space("New Space", "A description")
    assert result["space"]["id"] == "new-space"
    assert result["already_exists"] is False

    req = responses.calls[1].request
    parsed_payload = json.loads(req.body)
    assert parsed_payload["name"] == "New Space"
    assert parsed_payload["description"] == "A description"

def test_update_page_invalid_mode():
    client = DocmostClient()
    with pytest.raises(ValueError, match="mode must be one of: replace, append, prepend"):
        client.update_page("page_id", title="New title", mode="invalid_mode")

def test_update_page_no_title_or_content():
    client = DocmostClient()
    with pytest.raises(ValueError, match="At least one of title or content is required."):
        client.update_page("page_id")

def test_create_page_missing_space_id():
    client = DocmostClient()
    with pytest.raises(ValueError, match="space_id is required."):
        client.create_page("", "Title")

@responses.activate
def test_create_space_conflict(mock_client, mock_config):
    # API returns 409 conflict
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/spaces/create",
        status=409,
        json={"error": "Space exists"}
    )
    # Then client will try to find it (return_existing policy)
    spaces_data = {
        "data": {
            "items": [{"id": "existing-space", "name": "Existing Space"}]
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/spaces",
        status=200,
        json=spaces_data
    )
    
    result = mock_client.create_space("Existing Space")
    assert result["space"]["id"] == "existing-space"
    assert result["already_exists"] is True

@responses.activate
def test_create_page(mock_client, mock_config):
    page_resp = {
        "data": {
            "id": "new-page",
            "title": "Welcome"
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/create",
        status=200,
        json=page_resp
    )
    
    result = mock_client.create_page("space1", "Welcome", "# Hello", "parent1")
    assert result["id"] == "new-page"

@responses.activate
def test_update_page(mock_client, mock_config):
    update_data = {
        "data": {
            "id": "page123",
            "title": "Updated Title"
        }
    }
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/update",
        status=200,
        json=update_data
    )
    
    result = mock_client.update_page("page123", title="Updated Title", mode="replace")
    assert result["title"] == "Updated Title"
    req = responses.calls[0].request
    assert json.loads(req.body)["title"] == "Updated Title"

@responses.activate
def test_duplicate_page(mock_client, mock_config):
    dup_data = {"data": {"id": "page-dup", "title": "Clone"}}
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/duplicate",
        status=200,
        json=dup_data
    )
    
    result = mock_client.duplicate_page("page123")
    assert result["id"] == "page-dup"

@responses.activate
def test_move_page(mock_client, mock_config):
    move_data = {"data": {"id": "page1", "parentPageId": "parent2"}}
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/move",
        status=200,
        json=move_data
    )
    
    result = mock_client.move_page("page1", new_parent_page_id="parent2")
    assert result["parentPageId"] == "parent2"

@responses.activate
def test_move_page_to_space(mock_client, mock_config):
    move_data = {"data": {"id": "page1", "spaceId": "space2"}}
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/pages/move-to-space",
        status=200,
        json=move_data
    )
    
    result = mock_client.move_page_to_space("page1", target_space_id="space2")
    assert result["spaceId"] == "space2"

@responses.activate
def test_create_comment(mock_client, mock_config):
    comment_data = {"data": {"id": "cmt1"}}
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/comments/create",
        status=200,
        json=comment_data
    )
    
    result = mock_client.create_comment("page1", "Hello World")
    assert result["id"] == "cmt1"

@responses.activate
def test_resolve_comment(mock_client, mock_config):
    resolve_data = {"data": {"id": "cmt1", "resolved": True}}
    responses.add(
        responses.POST,
        f"{mock_config['base_url']}/api/comments/resolve",
        status=200,
        json=resolve_data
    )
    
    result = mock_client.resolve_comment("cmt1", "Fixed it")
    assert result["resolved"] is True

def test_prosemirror_to_markdown():
    client = DocmostClient()
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Test Heading"}]
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world", "marks": [{"type": "bold"}]}
                ]
            }
        ]
    }
    
    md = client.prosemirror_to_markdown(content)
    assert md == "## Test Heading\n\nHello **world**"

def test_markdown_to_prosemirror():
    client = DocmostClient()
    md = "Hello **world**\n\n*test*"
    pm = client.markdown_to_prosemirror(md)
    assert pm["type"] == "doc"
    assert len(pm["content"]) == 2
    # Check bold formatting was parsed
    first_para = pm["content"][0]["content"]
    assert any(item.get("marks") == [{"type": "bold"}] for item in first_para)
