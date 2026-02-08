"""
Docmost MCP Server
Provides 3 tools: list_spaces, search_docs, get_page
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
            description="Search documentation in Docmost. Returns top 5 matching pages with titles, highlights, and slugIds. Optionally filter by space using spaceId (UUID).",
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
            return await handle_search_docs(client, query, space_id)

        elif name == "get_page":
            slug_id = arguments.get("slug_id", "")
            return await handle_get_page(client, slug_id)

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
    space_id: str | None
) -> list[TextContent]:
    """Handle search_docs tool."""
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    results = client.search(query, space_id)

    if not results:
        return [TextContent(type="text", text=f"No results found for: {query}")]

    # Take top 5 results
    top_results = results[:5]

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
    lines.append("*Use `get_page` with slug_id to get full page content.*")

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
