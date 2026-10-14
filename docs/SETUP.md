# Setup and operational runbook

This package connects a local CLI and MCP server to the standard Google Docs API. Google Cloud holds the API and OAuth configuration. The installed tool holds credentials privately and sends authenticated requests directly to Google. No Apps Script deployment, custom web endpoint, browser automation, or hosted MCP service is needed during ordinary use.

## Install and verify offline

```sh
git clone https://github.com/java-heapler/google-docs-mcp.git
cd google-docs-mcp
uv sync --locked
uv run pytest
uv build
uv tool install .
google-docs doctor
```

`doctor` is a local configuration inspection. It never refreshes a token or proves live access. `authenticated: false` and `network_checked: false` reflect that boundary; they do not assert that saved credentials have been revoked.

## Google Cloud and OAuth

1. Choose a Cloud project you are authorized to use. An existing project works; a new project is not required. If creating a project fails with `resourcemanager.projects.create`, that is a project permission issue, not a Docs API limitation.
2. Enable **Google Docs API** (`docs.googleapis.com`) in **APIs & Services → Library**. Enabling Sheets does not enable Docs. This package supplies its own local MCP server over the regular API.
3. Configure **Google Auth Platform** if needed. For an external app in Testing mode, add the exact signing-in account under **Audience → Test users**. Existing organizational restrictions still apply.
4. Use a **Desktop app** OAuth client. An existing authorized Desktop client can be reused; a separate client can provide operational separation. Download its JSON outside your source tree. An API key alone does not grant access to private documents.
5. Run the explicit login below. Select the intended account and grant the requested Docs access. The application requests `https://www.googleapis.com/auth/documents`, which permits document reads and writes within that account's access. It is not a per-document scope. This CLI does not implement a Google Picker flow.

```sh
mkdir -p "$HOME/.config/google-docs-mcp"
chmod 700 "$HOME/.config/google-docs-mcp"
# Put the downloaded Desktop client at this location, then:
chmod 600 "$HOME/.config/google-docs-mcp/client_secret.json"
google-docs auth login --client-secrets "$HOME/.config/google-docs-mcp/client_secret.json"
```

On macOS the login uses the default browser. Select the intended Google account when prompted.

The app opens a browser and listens on a random loopback port on `127.0.0.1` for up to 180 seconds. PKCE is enabled. A successful login saves the token atomically with mode `600` at `~/.config/google-docs-mcp/token.json`. Ordinary CLI/MCP operations never initiate browser login.

Use `auth login --token-file /absolute/private/token.json` for another token location, then set `GOOGLE_DOCS_TOKEN_FILE` to that location for subsequent commands and the MCP host. Tokens must be outside source repositories and not symlinks. Do not put tokens, client secrets, or service-account keys in Git or chat.

A Sheets token is not a Docs token. Reusing the Desktop client does not reuse authorization: run Docs login and preserve the Sheets token. Saved scope metadata is checked rather than silently relabeling an old token with new scopes. If scope validation fails, obtain fresh consent. External Testing-mode refresh tokens for these scopes generally expire after seven days; unattended use may require a suitable publishing configuration. Do not change a shared project's audience or publishing status as an incidental fix.

## Service accounts

Set `GOOGLE_DOCS_SERVICE_ACCOUNT_FILE` to a private service-account key JSON. This takes precedence over desktop OAuth. Share the target document with that service-account identity using the needed role. Service accounts are most useful for documents already shared with them; document creation can be restricted by Drive ownership/storage policy. This package does not provision shared drives or domain-wide delegation.

## MCP host and skill

Find the installed command with `command -v google-docs`. Most MCP hosts need absolute paths:

```json
{
  "mcpServers": {
    "google-docs": {
      "command": "/absolute/path/to/google-docs",
      "args": ["mcp"],
      "env": {"GOOGLE_DOCS_TOKEN_FILE": "/absolute/private/token.json"}
    }
  }
}
```

Install `skills/google-docs` into your agent's skill directory. The skill explains operation; the executable provides the API. Reconnect the MCP host after configuration or package changes. Keep stdout reserved for MCP protocol messages.

## Verify real access and edits

Use a document ID from an authorized document's URL to test a bounded read:

```sh
google-docs get DOCUMENT_ID
```

For write testing, create a new synthetic document through `create`, then repeat with `--confirm` within the authorized test scope. Read it to obtain its tab and revision IDs. Preview insertion, execute with the required revision, and read back. Test a stale revision after another successful edit; rejection must leave the newer content intact. Use the generic batch command for narrow style updates and verify formatting in structured output. Do not test on existing personal, shared, or production documents.

Google Docs indexes text with UTF-16 code units. Nested tabs each have their own content; reads request `includeTabsContent=true`. Convenience insert/replace commands require an explicit tab. Generic batch requests retain Google's defaults, which differ by operation: omitted tab targeting can affect the first tab or all tabs. Explicit targets are preferable when preserving other tabs matters.

`requiredRevisionId` is optional because some operations are independent of a prior read. Use it whenever an edit depends on positions or state read earlier. If it is stale, fetch and review a new plan. Do not retry without the guard. The API validates a batch atomically, but collaborators can make subsequent edits.

## Failure handling

| Symptom | Next step |
| --- | --- |
| OAuth 403: app restricted to testers | Add the exact account under the selected project's test users and restart login. |
| API disabled / permission denied | Verify Docs API is enabled in the credential's project and the selected account can access that document. |
| Missing or insufficient saved scopes | Run Docs login for fresh consent; do not reuse a Sheets token. |
| Token permissions rejected | Restrict the selected token to `600`; verify it is outside a Git repository and not a symlink. |
| Revision rejected | Read the document again, regenerate the edit, and review the new preview. |
| Timeout or disconnected write | Inspect actual document state before deciding whether to retry. The write may have succeeded. |
| Wrong text location | Check tab ID, UTF-16 index, segment, and current revision using structured `get`. |

API and OAuth calls have bounded network timeouts. The Docs transport disables automatic HTTP retries, redirects, and refresh-triggered write replay. Errors exposed to CLI/MCP omit raw remote bodies and credentials. A local preview does not check permissions, indexes against the live document, or the complete server-side request schema.

## Releasing and evidence

Run the locked test suite and build before publishing. Tests cover every runtime statement and branch, official discovery serialization, real stdio MCP calls, strict mutation intent, token safety, and a local server that receives a POST and disconnects. These tests are credential-free. Keep live verification evidence distinct from offline tests; see [verification](VERIFICATION.md).

GitHub Actions uses Python 3.11, 3.12, and 3.13. Check the pushed commit's workflow result. Never publish real document contents, account details, or credentials as fixtures. Public source does not expose locally stored credentials or Google documents.

## References

- [Google Docs Python quickstart](https://developers.google.com/workspace/docs/api/quickstart/python)
- [OAuth scopes](https://developers.google.com/workspace/docs/api/auth)
- [Document tabs](https://developers.google.com/workspace/docs/api/how-tos/tabs)
- [Batch updates and write control](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate)
- [Request reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request)
- [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Usage limits](https://developers.google.com/workspace/docs/api/limits)
