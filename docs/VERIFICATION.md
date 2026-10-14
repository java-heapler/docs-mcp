# Verification record

Verified on October 13, 2026. Automated tests are credential-free and repeatable; live checks used a newly created document containing only synthetic content.

## Automated gate

`uv run pytest`: **104 passed**, **331 statements and 102 branches, all covered (100%)**. No runtime coverage exclusions. `uv build` produced the wheel and source distribution. Skill frontmatter validation passed.

The suite checks nested document tabs, paragraphs, tables and table-of-contents extraction; legacy body fallback; tab-scoped replacements; UTF-16 index forwarding; required revisions; exact official discovery request serialization; malformed input; sanitized failures; secure credential persistence; scope checks; CLI command forwarding; MCP strict types; and actual stdio initialize/list/call behavior. The stdio preview test blocks and records socket connection attempts.

A real local HTTP server receives writes and tests disconnects, redirects, 401, and 503 responses. Each case observes exactly one POST. These tests exercise no-replay behavior beyond checking a mocked `num_retries=0` argument.

An independent reviewer exercised the protocol, transport, discovery, and installed wheel. Review identified a credential-path false positive for some installed-wheel layouts. It was fixed and covered by a regression; unpacked source distributions remain protected.

## Live API checks

The Google Docs API was enabled in the existing authorized Cloud project. The existing Desktop OAuth client was reused with fresh Docs consent. A separate private Docs token was created; the Sheets token was preserved. No billing or publishing-status changes were made.

Successful checks against a new synthetic document:

1. Installed CLI creates a document and the API returns its ID.
2. Local insertion preview leaves the document unchanged.
3. Tab-aware Unicode insertion reads back correctly.
4. A stale required revision is rejected; the attempted text does not appear.
5. Scoped replacement changes the expected text.
6. A narrow bold-style batch reads back with the expected text style.
7. Insertion after an emoji uses the correct UTF-16 index.
8. A two-by-two table is created and reads back structurally.
9. Replacement in the first tab preserves matching text in a second tab.
10. A nested child tab is created, written, and included in text extraction.
11. Text inserted in a table cell appears in body-text extraction.

Private verification scripts and result summaries live outside source control under `~/.local/share/docs-mcp/verification/`. The test document is retained as a synthetic fixture; this package does not implement Drive deletion. No existing document was used as a write fixture.

These checks validate the listed behaviors, not every Google Docs UI action or every possible batch request. Google remains responsible for full request-schema and document-state validation. GitHub Actions repeats the offline gate and build on Python 3.11, 3.12, and 3.13.
