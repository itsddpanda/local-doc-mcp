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
| **create_space** | Create a new space with optional idempotent behavior |
| **create_page** | Create a page in a space (Markdown content) |
| **update_page** | Update page title/content (replace/append/prepend modes) |
| **duplicate_page** | Duplicate a page recursively |
| **move_page** | Move a page within a space or hierarchy |
| **move_page_to_space** | Move a page to another space |
| **create_comment** | Create a page comment (Markdown converted to ProseMirror) |
| **resolve_comment** | Resolve a comment with an optional note |

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

This installs the core dependencies:
- [`mcp`](https://pypi.org/project/mcp/) — official Python SDK for building MCP servers
- [`requests`](https://pypi.org/project/requests/) — HTTP client for Docmost API calls

### 3. Local Development with Docker (Optional)

If you need a local Docmost instance for testing, you can use the provided Docker Compose setup:

```bash
cd container_docmost
docker compose up -d
```

This starts Docmost on `http://localhost:3000` (port `3001` if configured in host mapping) along with Postgres and Redis.

### 4. Configure credentials

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
  "timeout": 30,
  "page_content_format": "markdown",
  "create_space_conflict_policy": "return_existing",
  "duplicate_page_conflict_policy": "auto_suffix",
  "clear_parent_on_space_move": true
}
```

| Parameter | Description |
|-----------|-------------|
| `base_url` | URL of your Docmost instance (no trailing slash) |
| `email` | Email address for Docmost authentication |
| `password` | Password for Docmost authentication |
| `timeout` | HTTP request timeout in seconds |
| `page_content_format` | Page content format for create/update (default: `markdown`) |
| `create_space_conflict_policy` | `return_existing` or `error` on space name conflict |
| `duplicate_page_conflict_policy` | `auto_suffix` or `error` on title conflict |
| `clear_parent_on_space_move` | Clear parent when moving to another space (default: true) |

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

### Create a new space

```
Create a space named "Project Phoenix" with description "Q2 launch docs"
```

### Create a page

```
Create a page in space "SPACE_ID" titled "Kickoff Notes" with content "# Kickoff\n..."
```

### Update a page (append)

```
Append "## Decisions\n- ..." to page "PAGE_ID"
```

### Move a page

```
Move page "PAGE_ID" under parent "PARENT_ID" and set position "after:SIBLING_ID"
```

> **Note:** `move_page` passes position hints through to the Docmost API. If your Docmost version requires fractional indices, you may need to adjust the API payload or client logic.

### Comment and resolve

```
Add a comment to page "PAGE_ID": "Please review this section."
Resolve comment "COMMENT_ID" with note "Addressed in revision 3."
```

## Write tool error handling

- `create_space`: 409 conflicts return a clear error or the existing space (see `create_space_conflict_policy`).
- `create_page`: 404 for invalid `space_id`, 400 for invalid `parent_page_id`.
- `update_page`: 404 when page is missing; append/prepend requires `content`.
- `duplicate_page`: 404 when source page is missing; conflict handling depends on `duplicate_page_conflict_policy`.
- `move_page`: requires `new_parent_page_id` or `new_position`; rejects circular moves; invalid positions return 400.
- `create_comment`: 404 when page is missing; 401 if not authorized.
- `resolve_comment`: 404 when comment is missing; 403 if not authorized.

## How it works

1. The MCP client launches the server as a subprocess and communicates via **stdio** (stdin/stdout).
2. On the first API call, the server authenticates with your Docmost instance using email/password and receives a **JWT token** from the `Set-Cookie` header.
3. The token is cached in `token.json` for subsequent requests. If a request returns **401**, the server automatically re-authenticates and retries.
4. Page content is stored in Docmost as **ProseMirror JSON**. The server converts it to clean **Markdown** (headings, lists, tables, code blocks, images, links, etc.) before returning it to the client.

## Project structure

```
docmost-mcp/
├── .github/workflows/    # CI/CD pipelines (GitHub Actions)
├── container_docmost/    # Docker Compose setup for local testing
├── tests/                # Comprehensive unit test suite
├── mcp_server.py         # MCP server (11 tools)
├── docmost_client.py     # Docmost API client
├── requirements.txt      # Python dependencies
├── config.example.json   # Configuration template
├── config.json           # Your credentials (not in git)
├── token.json            # Cached JWT token (auto-generated)
├── .gitignore
└── README.md
```

## Testing & CI/CD

The project includes a comprehensive test suite covering both the API client and the MCP server handlers.

### Running tests locally

```bash
# Install test dependencies
pip install pytest pytest-asyncio responses coverage pytest-cov

# Run all tests
PYTHONPATH=. pytest tests/ -v

# Run tests with coverage report
PYTHONPATH=. pytest tests/ --cov=. --cov-report=term-missing
```

### CI/CD

GitHub Actions are configured in `.github/workflows/ci.yml` to automatically run tests on every push and pull request across multiple Python versions (3.10, 3.11, 3.12).

You can simulate the CI environment locally using [act](https://github.com/nektos/act):

```bash
act push -W .github/workflows/ci.yml
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
