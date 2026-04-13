"""
Docmost API Client
Handles authentication, token caching, and API requests.
"""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta
import threading

import requests


# Token expiry buffer: refresh if token is older than 23 hours (assuming 24h JWT lifetime)
TOKEN_EXPIRY_HOURS = 23
MAX_SPACE_NAME_LENGTH = 255
MAX_DUPLICATE_SUFFIX_ATTEMPTS = 10
DEFAULT_SPACE_CONFLICT_POLICY = "return_existing"
DEFAULT_DUPLICATE_CONFLICT_POLICY = "auto_suffix"
DEFAULT_PAGE_CONTENT_FORMAT = "markdown"


class DocmostClient:
    """Client for Docmost API with token caching and auto-refresh."""

    def __init__(self, config_path: str = "config.json", token_path: str = "token.json"):
        self.config_path = Path(config_path)
        self.token_path = Path(token_path)
        self.config = self._load_config()
        self.base_url = self.config["base_url"].rstrip("/")
        self.timeout = self.config.get("timeout", 30)
        # Credentials (renamed to admin_email/admin_password). Fall back to legacy email/password if present.
        self.admin_email = self.config.get("admin_email") or self.config.get("email")
        self.admin_password = self.config.get("admin_password") or self.config.get("password")
        if not self.admin_email or not self.admin_password:
            raise ValueError("Config must include admin_email and admin_password (or legacy email/password).")
        self.token: Optional[str] = None
        self.token_created_at: Optional[datetime] = None
        self._lock = threading.Lock()
        self._load_token()

    def _load_config(self) -> dict:
        """Load configuration from config.json."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_token(self) -> None:
        """Load cached token from token.json if exists and not expired."""
        if not self.token_path.exists():
            return
            
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.token = data.get("token")
                created_at_str = data.get("created_at")
                if created_at_str:
                    self.token_created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            self.token = None
            self.token_created_at = None

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
            "email": self.admin_email,
            "password": self.admin_password
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
        """
        Ensure we have a valid token, login if necessary or if expired.
        Thread-safe via lock.
        """
        with self._lock:
            if not self.token:
                self.login()
            elif self._is_token_expired():
                self.login()
            return self.token
    
    def _is_token_expired(self) -> bool:
        """Check if cached token has exceeded its expected lifetime."""
        if not self.token_created_at:
            return False
        expiry_threshold = datetime.now(timezone.utc) - timedelta(hours=TOKEN_EXPIRY_HOURS)
        return self.token_created_at < expiry_threshold

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
        response = self._request_raw(method, endpoint, payload, retry_on_401)
        
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have access to perform this operation.")
            
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _request_raw(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
        retry_on_401: bool = True
    ) -> requests.Response:
        """Make an authenticated API request and return the raw response."""
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
            return self._request_raw(method, endpoint, payload, retry_on_401=False)

        return response

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
        return result.get("data", {}).get("items", [])

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

    def create_space(self, name: str, description: Optional[str] = None) -> dict:
        """Create a new Docmost space with optional idempotency."""
        space_name = self._normalize_space_name(name)
        conflict_policy = self._get_conflict_policy(
            "create_space_conflict_policy",
            DEFAULT_SPACE_CONFLICT_POLICY,
            {"return_existing", "error"}
        )

        if conflict_policy == "return_existing":
            existing = self._find_space_by_name(space_name)
            if existing:
                return {"space": existing, "already_exists": True}

        payload = {
            "name": space_name,
            "slug": self._generate_slug(space_name)
        }
        if description:
            payload["description"] = description

        # Correct endpoint for space creation is /create
        response = self._request_raw("POST", "/api/spaces/create", payload)
        
        if response.status_code == 409:
            if conflict_policy == "return_existing":
                existing = self._find_space_by_name(space_name)
                if existing:
                    return {"space": existing, "already_exists": True}
            raise ValueError(f"Space already exists: {space_name}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")
        if response.status_code == 400:
            raise ValueError(f"Invalid space data provided: {response.text}")

        response.raise_for_status()
        # API returns { "success": true, "data": { ... } }
        data = response.json().get("data", response.json())
        return {"space": data, "already_exists": False}

    def create_page(
        self,
        space_id: str,
        title: str,
        content: Optional[str] = None,
        parent_page_id: Optional[str] = None
    ) -> dict:
        """Create a new page in a space using Markdown content."""
        space_id = self._require_string(space_id, "space_id")
        title = self._normalize_title(title)

        payload: dict = {
            "spaceId": space_id,
            "title": title
        }
        if content is not None:
            payload["content"] = content
            payload["format"] = self.config.get("page_content_format", DEFAULT_PAGE_CONTENT_FORMAT)
        if parent_page_id:
            payload["parentPageId"] = parent_page_id

        # Correct endpoint for page creation is /api/pages/create
        response = self._request_raw("POST", "/api/pages/create", payload)
        if response.status_code == 404:
            raise ValueError(f"Space/Page not found: {space_id}/{parent_page_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")
        if response.status_code == 400:
            raise ValueError(f"Invalid request data: {response.text}")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def update_page(
        self,
        page_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        mode: str = "replace"
    ) -> dict:
        """Update a page title and/or content with replace/append/prepend modes."""
        page_id = self._require_string(page_id, "page_id")
        mode = mode or "replace"
        if mode not in {"replace", "append", "prepend"}:
            raise ValueError("mode must be one of: replace, append, prepend")
        if title is None and content is None:
            raise ValueError("At least one of title or content is required.")

        payload: dict = {"pageId": page_id}
        if title is not None:
            payload["title"] = self._normalize_title(title, field_name="title")

        if content is not None:
            # Note: Docmost API handles append/prepend via 'operation' parameter
            # We skip local merging if the API supports it directly
            payload["content"] = content
            payload["format"] = self.config.get("page_content_format", DEFAULT_PAGE_CONTENT_FORMAT)
            payload["operation"] = mode
        elif mode in {"append", "prepend"}:
            raise ValueError("content is required when using append or prepend mode.")

        # Correct endpoint for page update is /api/pages/update (POST)
        response = self._request_raw("POST", "/api/pages/update", payload)
        if response.status_code == 404:
            raise ValueError(f"Page not found: {page_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def duplicate_page(self, page_id: str, new_title: Optional[str] = None) -> dict:
        """Duplicate a page (recursive) with optional title override."""
        page_id = self._require_string(page_id, "page_id")
        
        payload: dict = {"pageId": page_id}
        
        # Correct endpoint for duplication is /api/pages/duplicate (POST)
        response = self._request_raw("POST", "/api/pages/duplicate", payload)
        
        if response.status_code == 404:
            raise ValueError(f"Page not found: {page_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")

        response.raise_for_status()
        result = response.json().get("data", response.json())
        
        # If new_title requested, perform an update on the newly created page
        if new_title:
            new_page_id = result.get("id") or result.get("slugId")
            if new_page_id:
                try:
                    return self.update_page(new_page_id, title=new_title)
                except Exception:
                    # Return duplication result anyway with info about title fail
                    result["requested_title"] = new_title
                    return result
        
        return result

    def move_page(
        self,
        page_id: str,
        new_parent_page_id: Optional[str] = None,
        new_position: Optional[str] = None
    ) -> dict:
        """Move a page to a new parent and/or position."""
        page_id = self._require_string(page_id, "page_id")
        if not new_parent_page_id and not new_position:
            raise ValueError("new_parent_page_id or new_position is required.")

        payload: dict = {
            "pageId": page_id,
            "position": new_position or "last"
        }
        if new_parent_page_id:
            payload["parentPageId"] = new_parent_page_id

        # Correct endpoint for moving page is /api/pages/move (POST)
        response = self._request_raw("POST", "/api/pages/move", payload)
        if response.status_code == 404:
            raise ValueError(f"Page not found: {page_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")
        if response.status_code == 400:
            raise ValueError(f"Invalid move request: {response.text}")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def move_page_to_space(self, page_id: str, target_space_id: str) -> dict:
        """Move a page to another space (top-level by default)."""
        page_id = self._require_string(page_id, "page_id")
        target_space_id = self._require_string(target_space_id, "target_space_id")

        payload: dict = {
            "pageId": page_id,
            "spaceId": target_space_id
        }

        # Correct endpoint for moving to space is /api/pages/move-to-space (POST)
        response = self._request_raw("POST", "/api/pages/move-to-space", payload)
        if response.status_code == 404:
            raise ValueError(f"Page or space not found: {page_id} / {target_space_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def create_comment(
        self,
        page_id: str,
        content: str,
        parent_comment_id: Optional[str] = None
    ) -> dict:
        """Create a comment on a page using ProseMirror JSON."""
        page_id = self._require_string(page_id, "page_id")
        content = self._require_string(content, "content")

        payload: dict = {
            "pageId": page_id,
            "content": self.markdown_to_prosemirror(content)
        }
        if parent_comment_id:
            payload["parentCommentId"] = parent_comment_id

        # Correct endpoint for comment creation is /api/comments/create (POST)
        response = self._request_raw("POST", "/api/comments/create", payload)
        if response.status_code == 404:
            raise ValueError(f"Page not found: {page_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation.")
        if response.status_code == 400:
            raise ValueError(f"Invalid comment data: {response.text}")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def resolve_comment(self, comment_id: str, resolution_note: Optional[str] = None) -> dict:
        """Resolve a comment (Enterprise Edition)."""
        comment_id = self._require_string(comment_id, "comment_id")

        payload: dict = {
            "commentId": comment_id,
            "resolved": True
        }
        if resolution_note:
            payload["note"] = resolution_note

        # Correct endpoint for resolution is /api/comments/resolve (POST)
        response = self._request_raw("POST", "/api/comments/resolve", payload)
        if response.status_code == 404:
            raise ValueError(f"Comment not found: {comment_id}")
        if response.status_code == 403:
            raise ValueError("Permission denied: your account does not have write access to perform this operation. (Note: Resolving comments may also require Enterprise Edition)")

        response.raise_for_status()
        return response.json().get("data", response.json())

    def add_user(
        self,
        email: str,
        name: str,
        password: str,
        role: str = "member",
        group_ids: Optional[list[str]] = None
    ) -> dict:
        """Add a user by creating an invite and self-accepting it (self-hosted flow)."""
        email = self._require_string(email, "email")
        name = self._require_string(name, "name")
        password = self._require_string(password, "password")
        role = (role or "member").strip().lower()
        if role not in {"member", "admin"}:
            raise ValueError("role must be 'member' or 'admin'")

        # Step 1: create invite
        payload_invite: dict = {
            "emails": [email],
            "role": role,
            "groupIds": group_ids or []
        }
        res_invite = self._request("POST", "/api/workspace/invites/create", payload_invite)

        # Step 2: find invite id
        res_list = self._request("POST", "/api/workspace/invites", {"query": email, "limit": 1})
        inv_id = _get_nested(res_list, ["data", "items"], [])
        inv_id = inv_id[0].get("id") if inv_id else None
        if not inv_id:
            raise ValueError("Invite not found after creation; user may already exist or invite filtered out")

        # Step 3: get invite link (self-host)
        res_link = self._request("POST", "/api/workspace/invites/link", {"invitationId": inv_id})
        invite_link = _get_nested(res_link, ["data", "inviteLink"], "")
        if not invite_link or "token=" not in invite_link:
            raise ValueError("Invite link not returned (cloud instances may forbid link retrieval)")
        token = invite_link.split("token=", 1)[1]

        # Step 4: accept invite (creates user)
        payload_accept = {
            "invitationId": inv_id,
            "token": token,
            "name": name,
            "password": password
        }
        res_accept = self._request("POST", "/api/workspace/invites/accept", payload_accept)
        return {
            "invite": res_invite,
            "accept": res_accept,
            "invitationId": inv_id,
            "email": email,
            "role": role,
            "group_ids": group_ids or []
        }

    def prosemirror_to_markdown(self, content: dict) -> str:
        """
        Convert ProseMirror JSON content to Markdown.

        Args:
            content: ProseMirror document object

        Returns:
            Markdown string, or empty string if content is invalid (logs warning)
        """
        if not content or content.get("type") != "doc":
            # Silently return empty for invalid content - could add logging here
            return ""

        return self._convert_nodes(content.get("content", []))

    def _convert_nodes(self, nodes: list, indent: int = 0) -> str:
        """Recursively convert ProseMirror nodes to markdown."""
        result = []
        known_types = {
            "paragraph", "heading", "bulletList", "orderedList", "listItem",
            "codeBlock", "blockquote", "horizontalRule", "table", "embed", "image"
        }

        for node in nodes:
            node_type = node.get("type", "")

            if node_type not in known_types:
                # Unknown node type - skip but could log for debugging
                # print(f"Warning: Unknown node type '{node_type}' skipped")
                pass

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

    def markdown_to_prosemirror(self, markdown: str) -> dict:
        """Convert basic Markdown into a ProseMirror doc for comments."""
        paragraphs = []
        current = []
        for line in markdown.splitlines():
            if line.strip() == "":
                if current:
                    paragraphs.append(current)
                    current = []
                continue
            current.append(line)
        if current:
            paragraphs.append(current)

        content = []
        for para_lines in paragraphs:
            inline_nodes = []
            for i, line in enumerate(para_lines):
                inline_nodes.extend(self._parse_inline_markdown(line))
                if i < len(para_lines) - 1:
                    inline_nodes.append({"type": "hardBreak"})
            content.append({"type": "paragraph", "content": inline_nodes})

        return {"type": "doc", "content": content}

    def _parse_inline_markdown(self, text: str) -> list[dict]:
        """Parse a subset of inline Markdown into ProseMirror text nodes."""
        nodes = []
        i = 0
        while i < len(text):
            if text.startswith("**", i):
                end = text.find("**", i + 2)
                if end != -1:
                    nodes.append({
                        "type": "text",
                        "text": text[i + 2:end],
                        "marks": [{"type": "bold"}]
                    })
                    i = end + 2
                    continue
                nodes.append({"type": "text", "text": "**"})
                i += 2
                continue

            if text.startswith("~~", i):
                end = text.find("~~", i + 2)
                if end != -1:
                    nodes.append({
                        "type": "text",
                        "text": text[i + 2:end],
                        "marks": [{"type": "strike"}]
                    })
                    i = end + 2
                    continue
                nodes.append({"type": "text", "text": "~~"})
                i += 2
                continue

            if text.startswith("`", i):
                end = text.find("`", i + 1)
                if end != -1:
                    nodes.append({
                        "type": "text",
                        "text": text[i + 1:end],
                        "marks": [{"type": "code"}]
                    })
                    i = end + 1
                    continue
                nodes.append({"type": "text", "text": "`"})
                i += 1
                continue

            if text.startswith("*", i):
                end = text.find("*", i + 1)
                if end != -1:
                    nodes.append({
                        "type": "text",
                        "text": text[i + 1:end],
                        "marks": [{"type": "italic"}]
                    })
                    i = end + 1
                    continue
                nodes.append({"type": "text", "text": "*"})
                i += 1
                continue

            if text.startswith("[", i):
                end_text = text.find("]", i + 1)
                if end_text != -1 and end_text + 1 < len(text) and text[end_text + 1] == "(":
                    end_url = text.find(")", end_text + 2)
                    if end_url != -1:
                        link_text = text[i + 1:end_text]
                        href = text[end_text + 2:end_url]
                        if link_text:
                            nodes.append({
                                "type": "text",
                                "text": link_text,
                                "marks": [{"type": "link", "attrs": {"href": href}}]
                            })
                        i = end_url + 1
                        continue
                nodes.append({"type": "text", "text": "["})
                i += 1
                continue

            next_specials = [
                text.find("**", i + 1),
                text.find("~~", i + 1),
                text.find("`", i + 1),
                text.find("*", i + 1),
                text.find("[", i + 1)
            ]
            next_positions = [pos for pos in next_specials if pos != -1]
            next_index = min(next_positions) if next_positions else len(text)
            nodes.append({"type": "text", "text": text[i:next_index]})
            i = next_index

        return nodes

    def _require_string(self, value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required.")
        return value.strip()

    def _normalize_space_name(self, name: str) -> str:
        name = self._require_string(name, "name")
        if len(name) > MAX_SPACE_NAME_LENGTH:
            raise ValueError(f"Space name must be <= {MAX_SPACE_NAME_LENGTH} characters.")
        return name

    def _generate_slug(self, name: str) -> str:
        """Generate a valid slug (alphanumeric only) from a name."""
        import re
        # Remove non-alphanumeric, convert to lowercase
        slug = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        if len(slug) < 2:
            # Fallback for very short or non-alpha names
            import time
            slug = f"space{int(time.time()) % 10000}"
        return slug[:100]

    def _normalize_title(self, title: str, field_name: str = "title") -> str:
        return self._require_string(title, field_name)

    def _get_conflict_policy(self, key: str, default: str, allowed: set[str]) -> str:
        value = self.config.get(key, default)
        if value not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ValueError(f"Invalid {key} value: {value}. Allowed: {allowed_list}")
        return value

    def _find_space_by_name(self, name: str) -> Optional[dict]:
        target = name.strip().lower()
        for space in self.list_spaces():
            if space.get("name", "").strip().lower() == target:
                return space
        return None

    def _get_page_markdown(self, page_id: str) -> str:
        page = self.get_page(page_id)
        return self.prosemirror_to_markdown(page.get("content", {}))

    def _merge_markdown(self, existing: str, new_content: str, mode: str) -> str:
        if not existing:
            return new_content
        if not new_content:
            return existing

        if mode == "append":
            return f"{existing.rstrip()}\n\n{new_content.lstrip()}"
        if mode == "prepend":
            return f"{new_content.rstrip()}\n\n{existing.lstrip()}"
        return new_content

    def _copy_title_with_suffix(self, base_title: str, attempt: int) -> str:
        if attempt == 0:
            return base_title
        return f"{base_title} (copy {attempt})"

    def _validate_no_circular_reference(self, page_id: str, new_parent_id: str) -> None:
        current_id = new_parent_id
        seen = set()
        while current_id:
            if current_id == page_id:
                raise ValueError("Circular reference detected: cannot move page under its descendant.")
            if current_id in seen:
                break
            seen.add(current_id)
            parent_page = self.get_page(current_id)
            current_id = self._get_parent_id(parent_page)

    def _get_parent_id(self, page: dict) -> Optional[str]:
        for key in ("parentId", "parentPageId", "parent_id"):
            parent_id = page.get(key)
            if parent_id:
                return parent_id
        return None

    def _build_position_payload(self, new_position: str) -> dict:
        position = new_position.strip()
        if position in {"first", "last"}:
            return {"position": position}
        if position.startswith("after:"):
            sibling_id = position.split("after:", 1)[1].strip()
            if not sibling_id:
                raise ValueError("after:{sibling_id} requires a sibling id.")
            return {"afterPageId": sibling_id}
        raise ValueError("new_position must be one of: first, last, after:{sibling_id}")


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
