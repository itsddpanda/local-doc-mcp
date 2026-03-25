"""
Docmost MCP Server
Provides 11 tools: list_spaces, search_docs, get_page, create_space, create_page,
update_page, duplicate_page, move_page, move_page_to_space, create_comment, resolve_comment
"""

import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from docmost_client import DocmostClient


# Initialize server
server = Server("docmost-mcp")

# Initialize client (will be created on first use)
_client: DocmostClient | None = None


def get_client() -> DocmostClient:
    """Get or create Docmost client."""
    global _client
    if _client is None:
        # Look for config in same directory as this script
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"
        token_path = script_dir / "token.json"
        _client = DocmostClient(
            config_path=str(config_path),
            token_path=str(token_path)
        )
    return _client


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_spaces",
            description="List all available documentation spaces in Docmost. Returns space names, slugs, and IDs. Use this to discover available spaces before searching.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="search_docs",
            description="Search documentation in Docmost. Returns top results (default 5, max 20) matching titles, highlights, and slugIds. Optionally filter by space using spaceId (UUID).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    },
                    "space_id": {
                        "type": "string",
                        "description": "Optional: Space UUID to filter results (get from list_spaces)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_page",
            description="Get full content of a documentation page by its slugId. Returns page content converted to Markdown format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug_id": {
                        "type": "string",
                        "description": "Page slugId (from search results)"
                    }
                },
                "required": ["slug_id"]
            }
        ),
        Tool(
            name="create_space",
            description="Create a new documentation space. Returns the new space ID, name, and slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Space name (required)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional space description"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="create_page",
            description="Create a new page in a space using Markdown content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "space_id": {
                        "type": "string",
                        "description": "Target space UUID"
                    },
                    "title": {
                        "type": "string",
                        "description": "Page title"
                    },
                    "content": {
                        "type": "string",
                        "description": "Optional Markdown content"
                    },
                    "parent_page_id": {
                        "type": "string",
                        "description": "Optional parent page ID for nesting"
                    }
                },
                "required": ["space_id", "title"]
            }
        ),
        Tool(
            name="update_page",
            description="Update a page title/content. Supports replace, append, or prepend modes for content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional new title"
                    },
                    "content": {
                        "type": "string",
                        "description": "Optional Markdown content"
                    },
                    "mode": {
                        "type": "string",
                        "description": "Content update mode: replace, append, prepend",
                        "enum": ["replace", "append", "prepend"],
                        "default": "replace"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="duplicate_page",
            description="Duplicate a page (recursive) with optional title override.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID to duplicate"
                    },
                    "new_title": {
                        "type": "string",
                        "description": "Optional new title for the duplicate"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="move_page",
            description="Move a page to a new parent and/or position (first, last, after:{sibling_id}).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "new_parent_page_id": {
                        "type": "string",
                        "description": "Optional new parent page ID"
                    },
                    "new_position": {
                        "type": "string",
                        "description": "Optional position: first, last, after:{sibling_id}"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="move_page_to_space",
            description="Move a page to another space (becomes top-level by default).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "target_space_id": {
                        "type": "string",
                        "description": "Target space UUID"
                    }
                },
                "required": ["page_id", "target_space_id"]
            }
        ),
        Tool(
            name="create_comment",
            description="Create a comment on a page (Markdown input converted to ProseMirror).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "Comment content in Markdown"
                    },
                    "parent_comment_id": {
                        "type": "string",
                        "description": "Optional parent comment ID for replies"
                    }
                },
                "required": ["page_id", "content"]
            }
        ),
        Tool(
            name="resolve_comment",
            description="Resolve a comment with an optional resolution note.",
            inputSchema={
                "type": "object",
                "properties": {
                    "comment_id": {
                        "type": "string",
                        "description": "Comment ID"
                    },
                    "resolution_note": {
                        "type": "string",
                        "description": "Optional resolution note"
                    }
                },
                "required": ["comment_id"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    try:
        client = get_client()

        if name == "list_spaces":
            return await handle_list_spaces(client)

        elif name == "search_docs":
            query = arguments.get("query", "")
            space_id = arguments.get("space_id")
            max_results = arguments.get("max_results", 5)
            return await handle_search_docs(client, query, space_id, max_results)

        elif name == "get_page":
            slug_id = arguments.get("slug_id", "")
            return await handle_get_page(client, slug_id)

        elif name == "create_space":
            name = arguments.get("name", "")
            description = arguments.get("description")
            return await handle_create_space(client, name, description)

        elif name == "create_page":
            space_id = arguments.get("space_id", "")
            title = arguments.get("title", "")
            content = arguments.get("content")
            parent_page_id = arguments.get("parent_page_id")
            return await handle_create_page(client, space_id, title, content, parent_page_id)

        elif name == "update_page":
            page_id = arguments.get("page_id", "")
            title = arguments.get("title")
            content = arguments.get("content")
            mode = arguments.get("mode", "replace")
            return await handle_update_page(client, page_id, title, content, mode)

        elif name == "duplicate_page":
            page_id = arguments.get("page_id", "")
            new_title = arguments.get("new_title")
            return await handle_duplicate_page(client, page_id, new_title)

        elif name == "move_page":
            page_id = arguments.get("page_id", "")
            new_parent_page_id = arguments.get("new_parent_page_id")
            new_position = arguments.get("new_position")
            return await handle_move_page(client, page_id, new_parent_page_id, new_position)

        elif name == "move_page_to_space":
            page_id = arguments.get("page_id", "")
            target_space_id = arguments.get("target_space_id", "")
            return await handle_move_page_to_space(client, page_id, target_space_id)

        elif name == "create_comment":
            page_id = arguments.get("page_id", "")
            content = arguments.get("content", "")
            parent_comment_id = arguments.get("parent_comment_id")
            return await handle_create_comment(client, page_id, content, parent_comment_id)

        elif name == "resolve_comment":
            comment_id = arguments.get("comment_id", "")
            resolution_note = arguments.get("resolution_note")
            return await handle_resolve_comment(client, comment_id, resolution_note)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_list_spaces(client: DocmostClient) -> list[TextContent]:
    """Handle list_spaces tool."""
    spaces = client.list_spaces()

    if not spaces:
        return [TextContent(type="text", text="No spaces found.")]

    lines = ["## Available Documentation Spaces", ""]
    lines.append("| Name | Slug | ID |")
    lines.append("|------|------|-----|")

    for space in spaces:
        name = space.get("name", "Unknown")
        slug = space.get("slug", "-")
        space_id = space.get("id", "-")
        lines.append(f"| {name} | {slug} | {space_id} |")

    lines.append("")
    lines.append(f"*Total: {len(spaces)} spaces*")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_search_docs(
    client: DocmostClient,
    query: str,
    space_id: str | None,
    max_results: int = 5
) -> list[TextContent]:
    """Handle search_docs tool."""
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    # Clamp max_results between 1 and 20
    max_results = max(1, min(20, max_results))

    results = client.search(query, space_id)

    if not results:
        return [TextContent(type="text", text=f"No results found for: {query}")]

    # Take top results (capped at max_results)
    top_results = results[:max_results]

    lines = [f"## Search Results for \"{query}\"", ""]

    for i, result in enumerate(top_results, 1):
        title = result.get("title", "Untitled")
        icon = result.get("icon", "")
        slug_id = result.get("slugId", "")
        space_name = result.get("space", {}).get("name", "Unknown")
        highlight = result.get("highlight", "")

        # Clean up highlight - remove HTML tags, keep as preview
        highlight_clean = highlight.replace("<b>", "**").replace("</b>", "**")

        lines.append(f"### {i}. {icon} {title}")
        lines.append(f"- **Space:** {space_name}")
        lines.append(f"- **Slug ID:** `{slug_id}`")
        if highlight_clean:
            lines.append(f"- **Preview:** {highlight_clean}")
        lines.append("")

    lines.append(f"*Showing {len(top_results)} of {len(results)} results*")
    lines.append("")
    lines.append(f"*Use `get_page` with slug_id to get full page content (max_results={max_results}).*")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_get_page(client: DocmostClient, slug_id: str) -> list[TextContent]:
    """Handle get_page tool."""
    if not slug_id:
        return [TextContent(type="text", text="Error: slug_id is required")]

    page = client.get_page(slug_id)

    if not page:
        return [TextContent(type="text", text=f"Page not found: {slug_id}")]

    title = page.get("title", "Untitled")
    icon = page.get("icon", "")
    space = page.get("space", {})
    space_name = space.get("name", "Unknown")
    creator = page.get("creator", {}).get("name", "Unknown")
    updated_at = page.get("updatedAt", "")[:10] if page.get("updatedAt") else ""

    # Convert content to markdown
    content = page.get("content", {})
    content_md = client.prosemirror_to_markdown(content)

    lines = [
        f"# {icon} {title}",
        "",
        f"**Space:** {space_name}",
        f"**Author:** {creator}",
        f"**Last Updated:** {updated_at}",
        "",
        "---",
        "",
        content_md
    ]

    return [TextContent(type="text", text="\n".join(lines))]


def _get_nested(data: dict, path: list[str], default: str = "") -> str:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


async def handle_create_space(
    client: DocmostClient,
    name: str,
    description: str | None
) -> list[TextContent]:
    """Handle create_space tool."""
    if not name:
        return [TextContent(type="text", text="Error: name is required")]

    result = client.create_space(name, description)
    space = result.get("space", {})
    already_exists = result.get("already_exists", False)

    lines = ["## Space Result", ""]
    lines.append(f"- **Name:** {space.get('name', 'Unknown')}")
    lines.append(f"- **ID:** {space.get('id', '-')}")
    lines.append(f"- **Slug:** {space.get('slug', '-')}")
    if already_exists:
        lines.append("- **Status:** Returned existing space (idempotent)")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_create_page(
    client: DocmostClient,
    space_id: str,
    title: str,
    content: str | None,
    parent_page_id: str | None
) -> list[TextContent]:
    """Handle create_page tool."""
    if not space_id or not title:
        return [TextContent(type="text", text="Error: space_id and title are required")]

    page = client.create_page(space_id, title, content, parent_page_id)

    page_id = page.get("id") or page.get("pageId") or page.get("slugId", "-")
    space_id_out = page.get("spaceId") or _get_nested(page, ["space", "id"], space_id)

    lines = ["## Page Created", ""]
    lines.append(f"- **Title:** {page.get('title', title)}")
    lines.append(f"- **Page ID:** {page_id}")
    lines.append(f"- **Space ID:** {space_id_out}")
    if parent_page_id:
        lines.append(f"- **Parent Page ID:** {parent_page_id}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_update_page(
    client: DocmostClient,
    page_id: str,
    title: str | None,
    content: str | None,
    mode: str
) -> list[TextContent]:
    """Handle update_page tool."""
    if not page_id:
        return [TextContent(type="text", text="Error: page_id is required")]

    page = client.update_page(page_id, title, content, mode)
    updated_title = page.get("title") or title or "Untitled"
    updated_at = page.get("updatedAt", "")

    lines = ["## Page Updated", ""]
    lines.append(f"- **Page ID:** {page.get('id', page_id)}")
    lines.append(f"- **Title:** {updated_title}")
    if updated_at:
        lines.append(f"- **Updated At:** {updated_at}")
    lines.append(f"- **Mode:** {mode}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_duplicate_page(
    client: DocmostClient,
    page_id: str,
    new_title: str | None
) -> list[TextContent]:
    """Handle duplicate_page tool."""
    if not page_id:
        return [TextContent(type="text", text="Error: page_id is required")]

    result = client.duplicate_page(page_id, new_title)
    new_page_id = result.get("id") or result.get("pageId") or result.get("slugId", "-")
    new_page_title = result.get("title") or result.get("requested_title") or "Untitled"
    space_id = result.get("spaceId") or _get_nested(result, ["space", "id"], "-")

    lines = ["## Page Duplicated", ""]
    lines.append(f"- **New Page ID:** {new_page_id}")
    lines.append(f"- **Title:** {new_page_title}")
    lines.append(f"- **Space ID:** {space_id}")
    requested = result.get("requested_title")
    if requested and requested != new_page_title:
        lines.append(f"- **Requested Title:** {requested}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_move_page(
    client: DocmostClient,
    page_id: str,
    new_parent_page_id: str | None,
    new_position: str | None
) -> list[TextContent]:
    """Handle move_page tool."""
    if not page_id:
        return [TextContent(type="text", text="Error: page_id is required")]
    if not new_parent_page_id and not new_position:
        return [TextContent(type="text", text="Error: new_parent_page_id or new_position is required")]

    result = client.move_page(page_id, new_parent_page_id, new_position)
    moved_at = result.get("updatedAt", "")
    parent_out = result.get("parentPageId") or new_parent_page_id or "-"

    lines = ["## Page Moved", ""]
    lines.append(f"- **Page ID:** {result.get('id', page_id)}")
    lines.append(f"- **New Parent ID:** {parent_out}")
    if new_position:
        lines.append(f"- **Position:** {new_position}")
    if moved_at:
        lines.append(f"- **Moved At:** {moved_at}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_move_page_to_space(
    client: DocmostClient,
    page_id: str,
    target_space_id: str
) -> list[TextContent]:
    """Handle move_page_to_space tool."""
    if not page_id or not target_space_id:
        return [TextContent(type="text", text="Error: page_id and target_space_id are required")]

    result = client.move_page_to_space(page_id, target_space_id)
    moved_at = result.get("updatedAt", "")
    space_id = result.get("spaceId") or target_space_id

    lines = ["## Page Moved To Space", ""]
    lines.append(f"- **Page ID:** {result.get('id', page_id)}")
    lines.append(f"- **New Space ID:** {space_id}")
    if moved_at:
        lines.append(f"- **Moved At:** {moved_at}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_create_comment(
    client: DocmostClient,
    page_id: str,
    content: str,
    parent_comment_id: str | None
) -> list[TextContent]:
    """Handle create_comment tool."""
    if not page_id or not content:
        return [TextContent(type="text", text="Error: page_id and content are required")]

    comment = client.create_comment(page_id, content, parent_comment_id)
    comment_id = comment.get("id") or comment.get("commentId", "-")
    created_at = comment.get("createdAt", "")
    author_id = _get_nested(comment, ["author", "id"], "-")

    lines = ["## Comment Created", ""]
    lines.append(f"- **Comment ID:** {comment_id}")
    lines.append(f"- **Page ID:** {page_id}")
    if created_at:
        lines.append(f"- **Created At:** {created_at}")
    if author_id != "-":
        lines.append(f"- **Author ID:** {author_id}")
    if parent_comment_id:
        lines.append(f"- **Parent Comment ID:** {parent_comment_id}")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_resolve_comment(
    client: DocmostClient,
    comment_id: str,
    resolution_note: str | None
) -> list[TextContent]:
    """Handle resolve_comment tool."""
    if not comment_id:
        return [TextContent(type="text", text="Error: comment_id is required")]

    result = client.resolve_comment(comment_id, resolution_note)
    resolved_at = result.get("resolvedAt", "")
    resolved_by = _get_nested(result, ["resolvedBy", "id"], _get_nested(result, ["resolver", "id"], ""))

    lines = ["## Comment Resolved", ""]
    lines.append(f"- **Comment ID:** {comment_id}")
    if resolved_at:
        lines.append(f"- **Resolved At:** {resolved_at}")
    if resolved_by:
        lines.append(f"- **Resolved By:** {resolved_by}")
    if resolution_note:
        lines.append(f"- **Resolution Note:** {resolution_note}")

    return [TextContent(type="text", text="\n".join(lines))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
