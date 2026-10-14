# google-docs-mcp

Google Docs from a CLI or an MCP agent, backed by Google's official Docs API. Uses the same preview-first architecture as [google-sheets-mcp](https://github.com/java-heapler/google-sheets-mcp).

## What it does

- Read structured documents, including nested tabs, or extract body text from paragraphs and tables.
- Create documents, insert text into a specific tab, and replace matching text within a tab.
- Submit Docs `batchUpdate` requests for text styles, paragraph styles, tables, images, lists, and other supported Docs API operations.
- Guard edits with a required document revision to reject changes based on stale reads.
- Preview mutations locally without credentials or network access. Execute explicitly with `--confirm` or MCP `confirm=true`.

This covers the Docs API, not every action in the Google Docs UI. File discovery, sharing, copying, deletion, and PDF/DOCX export belong to the Drive API and are not implemented here. Plain-text extraction reads body content; use structured `get` output for headers, footers, footnotes, images, styles, and suggestions.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/java-heapler/google-docs-mcp.git
google-docs --help
google-docs doctor
```

Enable **Google Docs API** in your Google Cloud project, configure a Desktop OAuth client, and run:

```sh
google-docs auth login --client-secrets /absolute/private/client_secret.json
```

See the [setup runbook](docs/SETUP.md) for consent, test users, credential storage, service accounts, and troubleshooting. The token is separate from Sheets at `~/.config/google-docs-mcp/token.json`.

## Examples

```sh
google-docs get DOCUMENT_ID
google-docs text DOCUMENT_ID
# Local preview, then authorized execution:
google-docs create 'Project notes'
google-docs create 'Project notes' --confirm
google-docs insert DOCUMENT_ID --tab TAB_ID --index 1 --text 'Project overview' --revision REVISION_ID
google-docs replace DOCUMENT_ID --tab TAB_ID --text '{{name}}' --replacement 'Example' --revision REVISION_ID
google-docs batch DOCUMENT_ID --requests changes.json --revision REVISION_ID
```

Add `--confirm` to an authorized edit to execute it. Read back the document afterward. IDs and revision IDs come from `get`; document IDs are the `/d/…/` portion of a Docs URL. Indexes are **UTF-16 code units**, not Python character offsets. An emoji may occupy two units. Helpers require a tab ID. Generic batches follow Google's request-specific tab defaults, so specify tab IDs in the requests.

Example `changes.json` making the first five UTF-16 units bold:

```json
[{"updateTextStyle":{"range":{"tabId":"TAB_ID","startIndex":1,"endIndex":6},"textStyle":{"bold":true},"fields":"bold"}}]
```

Batch previews validate the local payload shape and JSON values. They do not check remote document bounds, current revisions, permissions, or every Google request field. Google validates the complete batch when it executes it. Avoid broad `fields: "*"` updates when a targeted field mask will preserve unrelated formatting.

## MCP

```json
{"mcpServers":{"google-docs":{"command":"/absolute/path/to/google-docs","args":["mcp"]}}}
```

Use `command -v google-docs` to obtain the executable path. Seven tools expose document reads, text extraction, creation, batch edits, insertion, replacement, and local credential diagnostics. CLI and MCP share the same client. The [agent skill](skills/google-docs/SKILL.md) supplies operating instructions.

Confirmation is execution intent, not proof of user authorization. Writes do not automatically retry, including after a lost connection. An error can follow a successful write; inspect actual document state before deciding whether another attempt is necessary.

## Development

```sh
uv sync --locked
uv run pytest
uv build
```

CI tests Python 3.11, 3.12, and 3.13. The gate requires **100% statement and branch coverage**, with no runtime modules excluded. Tests include official discovery serialization, a real MCP stdio session, credential-free previews, revision handling, nested document structures, and a local HTTP server that disconnects after receiving a write. Offline tests do not require Google credentials. Coverage measures exercised paths, not every possible Google Docs behavior.
