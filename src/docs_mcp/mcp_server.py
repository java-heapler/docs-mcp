"""Official MCP stdio server for Google Docs."""
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import StrictBool, StrictInt, StrictStr

from . import auth
from .client import DocsClient

mcp = FastMCP('google-docs', instructions='Read Google Docs and preview mutations. Set confirm=true only with explicit user authorization. Indexes are UTF-16 code units. Never blindly retry uncertain writes.')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)
LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=LOCAL)
def docs_doctor() -> dict[str, Any]:
    """Inspect local credential configuration; does not test server authorization."""
    return auth.doctor()


@mcp.tool(annotations=READ)
def docs_get(document_id: StrictStr) -> dict[str, Any]:
    """Read the raw document including all tabs and their IDs."""
    return DocsClient().get_document(document_id)


@mcp.tool(annotations=READ)
def docs_text(document_id: StrictStr) -> dict[str, Any]:
    """Read body text by tab, recursively including tables and child tabs."""
    return DocsClient().read_text(document_id)


@mcp.tool(annotations=CREATE)
def docs_create(title: StrictStr, confirm: StrictBool = False) -> dict[str, Any]:
    """Preview a new document locally; confirm only with user authorization."""
    return DocsClient().create_document(title, confirm=confirm)


@mcp.tool(annotations=WRITE)
def docs_batch(document_id: StrictStr, requests: list[dict[str, Any]], required_revision_id: StrictStr | None = None, confirm: StrictBool = False) -> dict[str, Any]:
    """Preview raw Docs batchUpdate requests. API validates full schemas on execution."""
    return DocsClient().batch_update(document_id, requests, required_revision_id=required_revision_id, confirm=confirm)


@mcp.tool(annotations=CREATE)
def docs_insert(document_id: StrictStr, text: StrictStr, tab_id: StrictStr, index: StrictInt = 1, required_revision_id: StrictStr | None = None, confirm: StrictBool = False) -> dict[str, Any]:
    """Preview inserting text into an explicit tab at a UTF-16 code-unit index."""
    return DocsClient().insert_text(document_id, text, tab_id, index=index, required_revision_id=required_revision_id, confirm=confirm)


@mcp.tool(annotations=WRITE)
def docs_replace(document_id: StrictStr, text: StrictStr, replacement: StrictStr, tab_id: StrictStr, match_case: StrictBool = True, required_revision_id: StrictStr | None = None, confirm: StrictBool = False) -> dict[str, Any]:
    """Preview replacing matching text in one explicit tab, optionally requiring a revision."""
    return DocsClient().replace_text(document_id, text, replacement, tab_id, match_case=match_case, required_revision_id=required_revision_id, confirm=confirm)


def run():
    mcp.run(transport='stdio')
