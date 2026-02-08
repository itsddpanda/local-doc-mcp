# Docmost MCP Server

An [MCP](https://modelcontextprotocol.io/) server that gives AI assistants direct access to your self-hosted [Docmost](https://docmost.com/) documentation via its API.

Works with any MCP-compatible client, including:

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) / [Claude Desktop](https://claude.ai/download)
- [Cursor](https://www.cursor.com/)
- [Windsurf](https://windsurf.com/)
- [VS Code (GitHub Copilot)](https://code.visualstudio.com/)
- [Cline](https://github.com/cline/cline)
- [Continue](https://continue.dev/)
- [Zed](https://zed.dev/)

## Features

| Tool | Description |
|------|-------------|
| **list_spaces** | List all available documentation spaces with names, slugs, and IDs |
| **search_docs** | Full-text search across all documentation, with optional space filtering |
| **get_page** | Retrieve full page content converted from ProseMirror JSON to Markdown |

## Prerequisites

- Python 3.10+
- A running Docmost instance with valid user credentials
- An MCP-compatible client (Claude Code, Claude Desktop, Cursor, VS Code, etc.)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/aleksvin8888/local-docmost-mcp.git
cd docmost-mcp
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate   # Linux / macOS
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

This installs two dependencies:
- [`mcp`](https://pypi.org/project/mcp/) — official Python SDK for building MCP servers
- [`requests`](https://pypi.org/project/requests/) — HTTP client for Docmost API calls

### 3. Configure credentials

Copy the example config and fill in your details:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "base_url": "https://your-docmost-instance.example.com",
  "email": "your-email@example.com",
  "password": "your-password",
  "timeout": 30
}
```

| Parameter | Description |
|-----------|-------------|
| `base_url` | URL of your Docmost instance (no trailing slash) |
| `email` | Email address for Docmost authentication |
| `password` | Password for Docmost authentication |
| `timeout` | HTTP request timeout in seconds |

> **Note:** `config.json` contains sensitive credentials and is excluded from version control via `.gitignore`.

### 4. Verify the setup

```bash
source venv/bin/activate   # if not already active

python docmost_client.py
```

Expected output:

```
=== Spaces ===
  My Space (my-space) - 019a2a69-...
  Another Space (another) - 019a5e21-...
  ...

=== Search 'example' ===
  Example Page Title - abc123def
  ...
```

If you see your spaces and search results, the client is working correctly.

## Connecting to an MCP client

The server uses **stdio** transport, which is supported by all major MCP clients. Below are setup instructions for the most popular ones.

### Claude Code

Choose one of the following options.

> **Important:** Use **absolute paths** to both the Python binary inside `venv` and `mcp_server.py`.

### Option 1: Global config (recommended)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "docmost": {
      "command": "/absolute/path/to/docmost-mcp/venv/bin/python",
      "args": ["/absolute/path/to/docmost-mcp/mcp_server.py"]
    }
  }
}
```

### Option 2: Project-level config

Create `.claude/settings.json` in your project root:

```json
{
  "mcpServers": {
    "docmost": {
      "command": "/absolute/path/to/docmost-mcp/venv/bin/python",
      "args": ["/absolute/path/to/docmost-mcp/mcp_server.py"]
    }
  }
}
```

### Option 3: CLI command

```bash
claude mcp add docmost \
  -c "/absolute/path/to/docmost-mcp/venv/bin/python" \
  -- /absolute/path/to/docmost-mcp/mcp_server.py
```

After adding the config, restart Claude Code or start a new session.

### Claude Desktop

Add the server to your Claude Desktop config file:

- **Linux:** `~/.config/claude/claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "docmost": {
      "command": "/absolute/path/to/docmost-mcp/venv/bin/python",
      "args": ["/absolute/path/to/docmost-mcp/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop after saving the config.

### Cursor / Windsurf / VS Code / Other clients

Most MCP clients use the same configuration format. Add the server with:

- **Command:** `/absolute/path/to/docmost-mcp/venv/bin/python`
- **Args:** `/absolute/path/to/docmost-mcp/mcp_server.py`
- **Transport:** stdio

Refer to your client's documentation for the exact config file location and format.

## Usage

Once the MCP server is connected, your AI assistant can use the following tools:

### List all spaces

```
Show me all available documentation spaces
```

### Search documentation

```
Search the documentation for "user permissions"
```

### Search within a specific space

```
Find "API endpoints" in the Engineering space
```

### Get a specific page

```
Show me the full content of page with slug_id "abc123def"
```

## How it works

1. The MCP client launches the server as a subprocess and communicates via **stdio** (stdin/stdout).
2. On the first API call, the server authenticates with your Docmost instance using email/password and receives a **JWT token** from the `Set-Cookie` header.
3. The token is cached in `token.json` for subsequent requests. If a request returns **401**, the server automatically re-authenticates and retries.
4. Page content is stored in Docmost as **ProseMirror JSON**. The server converts it to clean **Markdown** (headings, lists, tables, code blocks, images, links, etc.) before returning it to the client.

## Project structure

```
docmost-mcp/
├── mcp_server.py         # MCP server (3 tools)
├── docmost_client.py     # Docmost API client
├── requirements.txt      # Python dependencies (mcp, requests)
├── config.example.json   # Configuration template
├── config.json           # Your credentials (not in git)
├── token.json            # Cached JWT token (auto-generated, not in git)
├── .gitignore
└── README.md
```

## Security

- `config.json` contains your credentials — **never commit it to git**
- `token.json` contains a JWT token — **never commit it to git**
- Both files are already listed in `.gitignore`

## Troubleshooting

### "No authToken in response cookies"
- Verify that `email` and `password` in `config.json` are correct
- Verify that `base_url` points to your Docmost instance

### "Connection refused"
- Check that your Docmost instance is running and accessible
- Check your network connection and firewall rules

### "401 Unauthorized"
- The token may have expired — delete `token.json` and it will be recreated automatically on the next request

### MCP tools not appearing in the client
- Ensure you used **absolute paths** to `venv/bin/python` and `mcp_server.py`
- Check that the virtual environment has all dependencies installed (`pip install -r requirements.txt`)
- Restart your MCP client after changing the config

## License

MIT
