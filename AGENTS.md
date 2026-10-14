# Contributor instructions

Use tools in `~/.config/tool-registry/registry.json` when available. Never send without the user's OK.

Use `uv sync --locked`, `uv run pytest`, and `uv build`. Preserve the 100% statement and branch coverage gate, including auth and interface modules. Test observable behavior, failure handling, actual MCP stdio, and Google discovery serialization. Never exclude runtime code to satisfy the gate.

CLI and MCP share DocsClient. Preview mutations without credentials or network; execute only within user authorization. Never blindly retry uncertain writes. Preserve explicit tab targeting in convenience methods and Google UTF-16 indexes. Use required revisions for edits based on a read. Keep credentials and real document contents out of source control. No live mutation tests against existing user documents; use an authorized synthetic document.
