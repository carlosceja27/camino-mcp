# Camino MCP

A local, **read-only** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Santa Clara University's Camino (Canvas LMS). Ask a compatible local AI client about courses, assignments, upcoming/overdue work, and visible grade summaries. Every user runs their own copy with their own Camino token. **This repository is not affiliated with or endorsed by Santa Clara University or Instructure.**

**No shared account or hosted service:** The server runs over local stdio. It makes HTTPS GET requests only to `https://camino.instructure.com/api/v1/`. No token, personal coursework, or institutional data is bundled with the code. Your chosen AI client *may send tool results to its model provider*; check its data policies and your institution's rules before connecting.

> **Web vs. local:** A GitHub URL is source code, **not** an MCP endpoint. You cannot upload this repository to ChatGPT, Gemini, or Claude in a browser and have its stdio tools run there. See [Browser-based ChatGPT, Gemini, and Claude](#browser-based-chatgpt-gemini-and-claude) for alternatives and limitations. Local clients (including Claude Code, Codex CLI, Gemini CLI, Hermes, Claude Desktop, and supported ChatGPT desktop clients) can run it directly.

## Requirements and installation

- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed on the machine that will run the MCP server.
- A Camino account allowed to create an API access token. Create one in **Camino → Account → Settings → Approved Integrations → New Access Token** (if enabled by your institution); give it a short expiration and revoke it when unused. Each person must create **their own** token.

```sh
git clone https://github.com/carlosceja27/camino-mcp.git
cd camino-mcp
uv sync --locked
# Launches the MCP stdio server; your MCP client normally starts this for you:
uv run --locked camino-mcp
```

Set `CAMINO_API_TOKEN` privately in the *MCP server process environment*. For a temporary terminal session, `read -r -s CAMINO_API_TOKEN; export CAMINO_API_TOKEN` (some shells require `read -s CAMINO_API_TOKEN` instead). For regular use, configure a **local, access-controlled secret manager or client-specific environment**. Do not put a real token in this repository, shared/project configs, command-line arguments, AI chats, or shell history. The server does **not** load `.env` or macOS Keychain automatically; if a token is missing, tools report an error without calling Camino. If your AI client is launched from the desktop, it may not inherit your shell's environment.

**Use absolute paths** in the examples below: replace `/absolute/path/to/uv` with the result of `command -v uv`, and `/absolute/path/to/camino-mcp` with your clone's absolute path. Keep client configuration **outside the public repository** and do not commit tokens. `uv run --locked --directory ...` uses the clone's lockfile without installing dev dependencies. Windows users: use absolute Windows paths and the appropriate executable name for `uv` (typically `uv.exe`); environment injection differs by shell/client.

## Local AI clients

### Claude Code

For a private user-level configuration rather than a project-shared `.mcp.json`:

```sh
claude mcp add --scope user --transport stdio camino -- /absolute/path/to/uv run --locked --directory /absolute/path/to/camino-mcp camino-mcp
```

Start Claude Code **from a session where `CAMINO_API_TOKEN` is already available to it**, then type `/mcp` to check connection. Do not use `--env CAMINO_API_TOKEN=...` with your actual token: client config could retain it. [Claude Code MCP docs](https://docs.anthropic.com/en/docs/claude-code/mcp).

### Codex CLI (and supported ChatGPT desktop MCP configuration)

In your private `~/.codex/config.toml`:

```toml
[mcp_servers.camino]
command = "/absolute/path/to/uv"
args = ["run", "--locked", "--directory", "/absolute/path/to/camino-mcp", "camino-mcp"]
env_vars = ["CAMINO_API_TOKEN"]
```

Launch Codex with that variable available in its environment; `env_vars` forwards the named variable without persisting its value in the TOML file. Check `/mcp` in Codex. OpenAI also documents a **ChatGPT desktop app** MCP settings panel with a local STDIO option; availability may vary by product and release. This is **not** ChatGPT in a browser. [Codex MCP docs](https://developers.openai.com/codex/mcp).

### Gemini CLI

In your private `~/.gemini/settings.json`, merge the following entry into the existing top-level `mcpServers` object (do not replace other settings):

```json
{
  "mcpServers": {
    "camino": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/camino-mcp", "camino-mcp"],
      "env": {"CAMINO_API_TOKEN": "$CAMINO_API_TOKEN"},
      "trust": false
    }
  }
}
```

Launch Gemini CLI from a session with `CAMINO_API_TOKEN` set. Gemini CLI explicitly expands `$CAMINO_API_TOKEN` from its environment; verify with `/mcp list`. [Gemini CLI MCP docs](https://geminicli.com/docs/tools/mcp-server/).

### Hermes Agent

Hermes filters tokens out of the environment inherited by stdio MCP subprocesses. Add the server using the documented `mcp_servers` key, through your private Hermes configuration workflow:

```yaml
mcp_servers:
  camino:
    command: "/absolute/path/to/uv"
    args: ["run", "--locked", "--directory", "/absolute/path/to/camino-mcp", "camino-mcp"]
```

**This will not authenticate by itself.** Users must explicitly supply `CAMINO_API_TOKEN` to this subprocess using their own secure, local-only credential injection (for example, a user-owned launcher that retrieves a token from an OS secret store, or private `env` configuration protected by filesystem permissions). Do not assume an exported shell variable is forwarded automatically, and never commit a credential-bearing configuration. Restart Hermes and check that its `mcp_camino_*` tools appear. [Hermes native MCP docs](https://hermes-agent.nousresearch.com/docs/).

### Claude Desktop and other local stdio clients

For a private local MCP config that supports the standard `mcpServers` shape:

```json
{
  "mcpServers": {
    "camino": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/camino-mcp", "camino-mcp"]
    }
  }
}
```

Provide the token to that client securely; desktop-launched apps often do not inherit shell exports. Claude Desktop local MCP servers run on your machine (unlike its web connectors). Each client has its own config path and support level. [Claude local MCP help](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

## Browser-based ChatGPT, Gemini, and Claude

| Browser product | What it expects | Can this repository be uploaded or pasted directly? |
| --- | --- | --- |
| [ChatGPT web MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) | An accessible **remote MCP endpoint** and eligible account/workspace features; OpenAI documents Secure MCP Tunnel for supported products. | **No.** A local stdio process is not a remote endpoint. |
| [Gemini web custom apps](https://support.google.com/gemini/answer/17209137?hl=en) | An MCP **server URL**; access is subject to Google's account, region, language, and feature requirements. | **No.** A GitHub clone/stdio command is not a URL for an MCP service. |
| [Claude web custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) | A reachable **remote MCP URL** from Anthropic's cloud, subject to plan and workspace rules. | **No.** Claude web cannot launch your local process. |

**This project does not implement a remote transport, OAuth, user isolation, or a hosted endpoint.** To use a browser product, *you* would need to deploy and secure a compatible remote MCP service (or a supported user-controlled tunnel/bridge where documented), with appropriate HTTPS, access control, per-user authentication, and institutional approval. Do **not** simply expose this stdio server or place a shared Camino token in an unauthenticated public wrapper. We do not provide or operate such a service, and we do not claim these browser paths are tested with this project. A self-hosted bridge also changes the privacy and maintenance model; local clients are the supported path here.

## Tools and behavior

- `list_courses`: merges paginated active, invited/pending, and favorite courses, deduplicated by numeric ID; **unstarred courses stay included**. Archived active enrollments may appear.
- `list_assignments(course_id, bucket?)`: validates a positive ASCII numeric course ID and requests submission metadata. Supported Canvas buckets: `future`, `past`, `overdue`, `upcoming`, `unsubmitted`, `ungraded`, `undated`.
- `upcoming(days=7)`: scans every returned course, including pending/unstarred, for unsubmitted dated assignments within the next 1–31 rolling 24-hour days.
- `overdue`: scans every returned course for past-due, unsubmitted dated assignments.
- `grades`: current enrollment grade/score, **when Canvas exposes it**; not a grade transcript.

Cross-course scans fail explicitly if any course request fails; no partial result is labeled complete. Successful tool responses include `"complete": true`; errors include `"complete": false`. Assignment HTML/descriptions and arbitrary Canvas fields are excluded. Only Camino HTTPS links are emitted. Returned course names and assignment titles are **untrusted data**, not instructions. Undated/invalid-date work is omitted from date-window tools; use `list_assignments` to inspect it. Dates are compared as timezone-aware instants.

## Security and limitations

- The server allows only HTTPS requests to Camino's Canvas API; redirects are disabled and pagination is restricted to the same endpoint. Requests time out; 429 responses get two short retries; pagination is capped at 20 pages and fails rather than silently truncating results.
- **Read-only means no Canvas writes**; any AI client granted these tools can still read and transmit the returned metadata. Use only a trusted client and handle student information under applicable institutional rules.
- **No live Camino account or real token was used in the automated tests.** Canvas overrides, grades, permissions, missing enrollments, and institution-specific behavior need verification with a consenting user before relying on them for deadlines.
- If your server returns an error, check your token, enrollment, or Camino availability. Do not paste tokens or full private tool responses into public bug reports.

## Development

```sh
uv sync --extra dev --locked
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked pytest -q --cov=camino_mcp --cov-report=term-missing
uv build --no-sources
```

The suite uses synthetic Canvas responses and an offline MCP stdio handshake. Contributions welcome; please include tests, and do not submit real coursework or tokens. The repository is distributed under [Apache License 2.0](LICENSE). The separate Camino Assistant skill inspired this implementation but is not bundled here.
