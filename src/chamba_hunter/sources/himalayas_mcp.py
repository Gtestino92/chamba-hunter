from dataclasses import dataclass
import json
import re
from typing import Any

import httpx


MCP_URL = "https://mcp.himalayas.app/mcp"
MCP_PROTOCOL_VERSION = "2025-11-25"

_WEBSITE_LINE = re.compile(
    r"(?im)^\s*(?:🌐\s*)?\*\*Website:\*\*\s*(.+?)\s*$"
)

_MARKDOWN_LINK = re.compile(
    r"^\[([^\]]+)\]\((https?://[^)]+)\)$"
)

_RAW_HTTP_URL = re.compile(
    r"https?://[^\s<>\]]+"
)


class HimalayasMcpError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HimalayasCompanyDetails:
    company_slug: str
    company_name: str
    raw_text: str
    website_url: str | None


class HimalayasMcpClient:
    def __init__(
        self,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._client: httpx.Client | None = None
        self._session_id: str | None = None
        self._request_id = 0

    def __enter__(
        self,
    ) -> "HimalayasMcpClient":
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1",
            },
        )

        self._initialize()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        if self._client is not None:
            self._client.close()

        self._client = None
        self._session_id = None

    def get_company_details(
        self,
        company_slug: str,
    ) -> HimalayasCompanyDetails:
        slug = company_slug.strip()

        if not slug:
            raise ValueError(
                "Himalayas company slug cannot be empty."
            )

        payload = self._request(
            method="tools/call",
            params={
                "name": "get_company_details",
                "arguments": {
                    "company_slug": slug,
                },
            },
            tool_name="get_company_details",
        )

        result = payload.get("result")

        if not isinstance(result, dict):
            raise HimalayasMcpError(
                "get_company_details returned no result object."
            )

        if result.get("isError") is True:
            raise HimalayasMcpError(
                "get_company_details returned isError=true: "
                f"{json.dumps(result, ensure_ascii=False)}"
            )

        content = result.get("content")

        if not isinstance(content, list):
            raise HimalayasMcpError(
                "get_company_details returned no content list."
            )

        text_parts: list[str] = []

        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") != "text":
                continue

            text = item.get("text")

            if isinstance(text, str):
                text_parts.append(text)

        raw_text = "\n".join(text_parts).strip()

        if not raw_text:
            raise HimalayasMcpError(
                "get_company_details returned no text content."
            )

        company_name = _extract_company_name(
            raw_text
        )

        if company_name is None:
            raise HimalayasMcpError(
                "get_company_details returned "
                "no company heading."
            )

        return HimalayasCompanyDetails(
            company_slug=slug,
            company_name=company_name,
            raw_text=raw_text,
            website_url=_extract_website_url(
                raw_text
            ),
        )

    def _initialize(
        self,
    ) -> None:
        client = self._require_client()

        response = client.post(
            MCP_URL,
            headers={
                "Accept": (
                    "application/json, "
                    "text/event-stream"
                ),
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": (
                        MCP_PROTOCOL_VERSION
                    ),
                    "capabilities": {},
                    "clientInfo": {
                        "name": "chamba-hunter",
                        "version": "0.1",
                    },
                },
            },
        )

        response.raise_for_status()

        initialize_payload = _parse_mcp_response(
            response
        )
        _raise_jsonrpc_error(
            initialize_payload
        )

        result = initialize_payload.get(
            "result"
        )

        if not isinstance(result, dict):
            raise HimalayasMcpError(
                "MCP initialize returned no result object."
            )

        negotiated = result.get(
            "protocolVersion"
        )

        if negotiated != MCP_PROTOCOL_VERSION:
            raise HimalayasMcpError(
                "Unexpected negotiated MCP protocol: "
                f"{negotiated!r}"
            )

        self._session_id = (
            response.headers.get(
                "Mcp-Session-Id"
            )
            or response.headers.get(
                "MCP-Session-Id"
            )
        )

        headers = self._headers()

        initialized = client.post(
            MCP_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": (
                    "notifications/initialized"
                ),
            },
        )

        initialized.raise_for_status()

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        client = self._require_client()

        headers = self._headers()

        if tool_name is not None:
            headers["Mcp-Name"] = tool_name

        response = client.post(
            MCP_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            },
        )

        response.raise_for_status()

        payload = _parse_mcp_response(
            response
        )
        _raise_jsonrpc_error(payload)

        return payload

    def _headers(
        self,
    ) -> dict[str, str]:
        headers = {
            "Accept": (
                "application/json, "
                "text/event-stream"
            ),
            "Content-Type": "application/json",
            "MCP-Protocol-Version": (
                MCP_PROTOCOL_VERSION
            ),
        }

        if self._session_id is not None:
            headers[
                "Mcp-Session-Id"
            ] = self._session_id

        return headers

    def _require_client(
        self,
    ) -> httpx.Client:
        if self._client is None:
            raise RuntimeError(
                "HimalayasMcpClient must be used "
                "as a context manager."
            )

        return self._client

    def _next_id(
        self,
    ) -> int:
        self._request_id += 1
        return self._request_id



def _extract_company_name(
    text: str,
) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()

        if not stripped.startswith("# "):
            continue

        name = stripped[2:].strip()

        if name:
            return name

    return None

def _extract_website_url(
    text: str,
) -> str | None:
    match = _WEBSITE_LINE.search(text)

    if match is None:
        return None

    value = match.group(1).strip()

    markdown_match = (
        _MARKDOWN_LINK.match(value)
    )

    if markdown_match is not None:
        return markdown_match.group(2)

    raw_match = _RAW_HTTP_URL.search(
        value
    )

    if raw_match is None:
        return None

    return raw_match.group(0).rstrip(
        ".,);"
    )


def _parse_mcp_response(
    response: httpx.Response,
) -> dict[str, Any]:
    content_type = (
        response.headers.get(
            "content-type",
            ""
        )
        .split(";", 1)[0]
        .strip()
        .casefold()
    )

    if content_type == "application/json":
        payload = response.json()

        if not isinstance(payload, dict):
            raise HimalayasMcpError(
                "Expected MCP JSON object."
            )

        return payload

    if content_type == "text/event-stream":
        payloads: list[
            dict[str, Any]
        ] = []

        for line in (
            response.text.splitlines()
        ):
            if not line.startswith(
                "data:"
            ):
                continue

            raw = line[
                len("data:"):
            ].strip()

            if not raw:
                continue

            try:
                parsed = json.loads(
                    raw
                )
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                payloads.append(
                    parsed
                )

        if not payloads:
            raise HimalayasMcpError(
                "MCP SSE response contained "
                "no JSON payload."
            )

        return payloads[-1]

    raise HimalayasMcpError(
        "Unexpected MCP content type: "
        f"{content_type!r}"
    )


def _raise_jsonrpc_error(
    payload: dict[str, Any],
) -> None:
    error = payload.get("error")

    if error is None:
        return

    raise HimalayasMcpError(
        "MCP JSON-RPC error: "
        f"{json.dumps(error, ensure_ascii=False)}"
    )
