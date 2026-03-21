import pytest
import json
from unittest.mock import patch, mock_open

@pytest.fixture
def mock_config():
    return {
        "base_url": "http://example.docmost.com",
        "email": "test@example.com",
        "password": "password123",
        "timeout": 10
    }

@pytest.fixture
def mock_token_data():
    return {
        "token": "fake-jwt-token",
        "created_at": "2026-03-22T00:00:00Z"
    }

@pytest.fixture
def mock_client(mock_config, mock_token_data):
    """Provides a DocmostClient with mocked filesystem operations."""
    config_json = json.dumps(mock_config)
    token_json = json.dumps(mock_token_data)
    
    def side_effect_open(filename, *args, **kwargs):
        if "config.json" in str(filename):
            return mock_open(read_data=config_json)(filename, *args, **kwargs)
        if "token.json" in str(filename):
            return mock_open(read_data=token_json)(filename, *args, **kwargs)
        return mock_open()(filename, *args, **kwargs)
        
    with patch("pathlib.Path.exists", return_value=True), \
         patch("builtins.open", side_effect=side_effect_open), \
         patch("fcntl.flock"):
         
        from docmost_client import DocmostClient
        client = DocmostClient()
        yield client
