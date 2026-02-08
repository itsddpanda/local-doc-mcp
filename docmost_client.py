"""
Docmost API Client
Handles authentication, token caching, and API requests.
"""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import requests


class DocmostClient:
    """Client for Docmost API with token caching and auto-refresh."""

    def __init__(self, config_path: str = "config.json", token_path: str = "token.json"):
        self.config_path = Path(config_path)
        self.token_path = Path(token_path)
        self.config = self._load_config()
        self.base_url = self.config["base_url"].rstrip("/")
        self.timeout = self.config.get("timeout", 30)
        self.token: Optional[str] = None
        self._load_token()

    def _load_config(self) -> dict:
        """Load configuration from config.json."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_token(self) -> None:
        """Load cached token from token.json if exists."""
        if self.token_path.exists():
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.token = data.get("token")
            except (json.JSONDecodeError, KeyError):
                self.token = None

    def _save_token(self) -> None:
        """Save token to token.json for reuse."""
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump({
                "token": self.token,
                "created_at": datetime.now(timezone.utc).isoformat()
            }, f, indent=2)

    def login(self) -> str:
        """
        Authenticate with Docmost and get JWT token.
        Token is returned via Set-Cookie header as 'authToken'.
        """
        url = f"{self.base_url}/api/auth/login"
        payload = {
            "email": self.config["email"],
            "password": self.config["password"]
        }

        response = requests.post(
            url,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()

        # Token comes from Set-Cookie header
        cookies = response.cookies
        token = cookies.get("authToken")

        if not token:
            raise ValueError("No authToken in response cookies. Login may have failed.")

        self.token = token
        self._save_token()
        return token

    def _ensure_token(self) -> str:
        """Ensure we have a valid token, login if necessary."""
        if not self.token:
            self.login()
        return self.token

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
        retry_on_401: bool = True
    ) -> dict:
        """
        Make an authenticated API request.
        Automatically retries with fresh token on 401.
        """
        self._ensure_token()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )

        # Handle 401 - token expired, re-login and retry
        if response.status_code == 401 and retry_on_401:
            self.login()
            return self._request(method, endpoint, payload, retry_on_401=False)

        response.raise_for_status()
        return response.json()

    def list_spaces(self, page: int = 1, limit: int = 100) -> list[dict]:
        """
        Get list of all spaces.

        Returns:
            List of space objects with id, name, slug, description, memberCount
        """
        result = self._request("POST", "/api/spaces", {"page": page, "limit": limit})
        return result.get("data", {}).get("items", [])

    def search(self, query: str, space_id: Optional[str] = None) -> list[dict]:
        """
        Search documents.

        Args:
            query: Search query string
            space_id: Optional space UUID to filter results

        Returns:
            List of search results with id, slugId, title, highlight, space info
        """
        payload = {"query": query}
        if space_id:
            payload["spaceId"] = space_id

        result = self._request("POST", "/api/search", payload)
        return result.get("data", [])

    def get_page(self, slug_id: str) -> dict:
        """
        Get page content by slugId.

        Args:
            slug_id: The slugId from search results

        Returns:
            Page object with title, content, creator, space info
        """
        result = self._request("POST", "/api/pages/info", {"pageId": slug_id})
        return result.get("data", {})

    def prosemirror_to_markdown(self, content: dict) -> str:
        """
        Convert ProseMirror JSON content to Markdown.

        Args:
            content: ProseMirror document object

        Returns:
            Markdown string
        """
        if not content or content.get("type") != "doc":
            return ""

        return self._convert_nodes(content.get("content", []))

    def _convert_nodes(self, nodes: list, indent: int = 0) -> str:
        """Recursively convert ProseMirror nodes to markdown."""
        result = []

        for node in nodes:
            node_type = node.get("type", "")

            if node_type == "paragraph":
                text = self._extract_text(node.get("content", []))
                if text:
                    result.append(text)
                result.append("")  # Empty line after paragraph

            elif node_type == "heading":
                level = node.get("attrs", {}).get("level", 1)
                text = self._extract_text(node.get("content", []))
                result.append(f"{'#' * level} {text}")
                result.append("")

            elif node_type == "bulletList":
                items = self._convert_list_items(node.get("content", []), bullet="- ", indent=indent)
                result.append(items)

            elif node_type == "orderedList":
                items = self._convert_list_items(node.get("content", []), numbered=True, indent=indent)
                result.append(items)

            elif node_type == "listItem":
                # Handled by parent list
                pass

            elif node_type == "codeBlock":
                lang = node.get("attrs", {}).get("language", "")
                text = self._extract_text(node.get("content", []))
                result.append(f"```{lang}")
                result.append(text)
                result.append("```")
                result.append("")

            elif node_type == "blockquote":
                inner = self._convert_nodes(node.get("content", []))
                quoted = "\n".join(f"> {line}" for line in inner.split("\n") if line)
                result.append(quoted)
                result.append("")

            elif node_type == "horizontalRule":
                result.append("---")
                result.append("")

            elif node_type == "table":
                table_md = self._convert_table(node)
                result.append(table_md)
                result.append("")

            elif node_type == "embed":
                src = node.get("attrs", {}).get("src", "")
                if src:
                    result.append(f"[Embedded content]({src})")
                    result.append("")

            elif node_type == "image":
                src = node.get("attrs", {}).get("src", "")
                alt = node.get("attrs", {}).get("alt", "image")
                if src:
                    result.append(f"![{alt}]({src})")
                    result.append("")

        return "\n".join(result).strip()

    def _extract_text(self, content: list) -> str:
        """Extract text from inline content with formatting."""
        parts = []

        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                marks = item.get("marks", [])

                for mark in marks:
                    mark_type = mark.get("type", "")
                    if mark_type == "bold":
                        text = f"**{text}**"
                    elif mark_type == "italic":
                        text = f"*{text}*"
                    elif mark_type == "code":
                        text = f"`{text}`"
                    elif mark_type == "strike":
                        text = f"~~{text}~~"
                    elif mark_type == "link":
                        href = mark.get("attrs", {}).get("href", "")
                        text = f"[{text}]({href})"

                parts.append(text)
            elif item.get("type") == "hardBreak":
                parts.append("\n")

        return "".join(parts)

    def _convert_list_items(
        self,
        items: list,
        bullet: str = "- ",
        numbered: bool = False,
        indent: int = 0
    ) -> str:
        """Convert list items to markdown."""
        result = []
        prefix = "  " * indent

        for i, item in enumerate(items):
            if item.get("type") != "listItem":
                continue

            item_content = item.get("content", [])

            # Get first paragraph text
            first_text = ""
            nested_content = []

            for node in item_content:
                if node.get("type") == "paragraph" and not first_text:
                    first_text = self._extract_text(node.get("content", []))
                elif node.get("type") in ("bulletList", "orderedList"):
                    nested_content.append(node)

            # Format bullet
            if numbered:
                marker = f"{i + 1}. "
            else:
                marker = bullet

            result.append(f"{prefix}{marker}{first_text}")

            # Handle nested lists
            for nested in nested_content:
                nested_md = self._convert_nodes([nested], indent=indent + 1)
                result.append(nested_md)

        return "\n".join(result)

    def _convert_table(self, table_node: dict) -> str:
        """Convert table node to markdown table."""
        rows = []

        for row_node in table_node.get("content", []):
            if row_node.get("type") != "tableRow":
                continue

            cells = []
            for cell_node in row_node.get("content", []):
                cell_type = cell_node.get("type", "")
                if cell_type in ("tableCell", "tableHeader"):
                    cell_content = self._convert_nodes(cell_node.get("content", []))
                    # Clean up cell content - single line
                    cell_text = " ".join(cell_content.split())
                    cells.append(cell_text)

            rows.append(cells)

        if not rows:
            return ""

        # Build markdown table
        lines = []

        # Header row
        if rows:
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")

        # Data rows
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)


# For testing
if __name__ == "__main__":
    client = DocmostClient()

    print("=== Spaces ===")
    spaces = client.list_spaces()
    for s in spaces:
        print(f"  {s['name']} ({s['slug']}) - {s['id']}")

    print("\n=== Search 'saas' ===")
    results = client.search("saas")
    for r in results[:3]:
        print(f"  {r['title']} - {r['slugId']}")

    if results:
        print(f"\n=== Page: {results[0]['title']} ===")
        page = client.get_page(results[0]['slugId'])
        md = client.prosemirror_to_markdown(page.get("content", {}))
        print(md[:500])
