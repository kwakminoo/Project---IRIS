# Iris Google Workspace Email

Iris Mail uses Gmail/Google Workspace as the source of truth. Iris stores only
account metadata, UI preferences, and action audit ids/hashes. It does not store
email bodies, full lists, snippets, attachment content, search result contents,
or raw thread payloads.

## MCP Server

Example streamable HTTP server:

```powershell
uvx workspace-mcp --transport streamable-http --tools gmail drive calendar docs sheets --tool-tier core
```

Configure Iris with either HTTP or stdio:

```powershell
GOOGLE_WORKSPACE_MCP_URL=http://127.0.0.1:8000/mcp
GOOGLE_WORKSPACE_MCP_COMMAND=
GOOGLE_WORKSPACE_MCP_AUTH_HEADER=
USER_GOOGLE_EMAIL=you@example.com
GOOGLE_MCP_CREDENTIALS_DIR=~/.iris/google-workspace/you@example.com
```

`USER_GOOGLE_EMAIL` must match the email saved in the Iris user profile. If it
does not match, Iris Mail blocks the connection.

## Tests

```powershell
python -m compileall iris -q
python -m pytest -q
```

Live tests are skipped unless explicitly enabled:

```powershell
$env:IRIS_ENABLE_LIVE_GOOGLE_WORKSPACE_TESTS="1"
$env:IRIS_ENABLE_LIVE_EMAIL_SEND_TESTS="1"
$env:IRIS_TEST_GOOGLE_EMAIL="you@example.com"
$env:IRIS_TEST_EXTERNAL_EMAIL="kwakmw12@naver.com"
$env:IRIS_CONFIRM_EXTERNAL_EMAIL_TEST="YES"
python -m pytest iris/tests/test_email_live_google_workspace.py -q
```

External send tests require both `IRIS_ENABLE_LIVE_EMAIL_SEND_TESTS=1` and
`IRIS_CONFIRM_EXTERNAL_EMAIL_TEST=YES`.
