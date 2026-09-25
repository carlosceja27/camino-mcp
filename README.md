# Camino MCP

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Santa Clara University's Camino (Canvas LMS). Read courses, assignments and instructions, pages, discussions, announcements, Canvas Inbox messages, and course files; optionally download files to an existing local directory. Every user runs their own copy with their own Camino token. **This repository is not affiliated with or endorsed by Santa Clara University or Instructure.**

**No shared account or hosted service:** The server runs over local stdio. It makes HTTPS GET requests to `https://camino.instructure.com/`, plus credential-free GET requests to allowlisted Canvas file CDN hosts when downloading. No token, personal coursework, or institutional data is bundled with the code. Your chosen AI client *may send tool results to its model provider*; check its data policies and your institution's rules before connecting.

> **Web vs. local:** A GitHub URL is source code, **not** an MCP endpoint. You cannot upload this repository to ChatGPT, Gemini, or Claude in a browser and have its stdio tools run there. See [Browser-based ChatGPT, Gemini, and Claude](#browser-based-chatgpt-gemini-and-claude) for alternatives and limitations. Local clients (including Claude Code, Codex CLI, Gemini CLI, Hermes, Claude Desktop, and supported ChatGPT desktop clients) can run it directly.

## Quick start (about 10 minutes)

1. **Install uv** (it installs Python for you): follow <https://docs.astral.sh/uv/getting-started/installation/>. On macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`. On Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
2. **Download this project** and install it (commands below).
3. **Create your Camino token** — see [Getting your Camino API token](#getting-your-camino-api-token).
4. **Connect your AI app** — pick yours under [Local AI clients](#local-ai-clients). Not sure? Claude Desktop is the easiest for non-programmers.
5. **Restart the AI app and ask:** *"Check my Camino setup"*, then *"What's due this week?"*

Ask your AI assistant to help with any step — this README includes a section written for it.

## Requirements and installation

- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed on the machine that will run the MCP server.
- A Camino account allowed to create an API access token. See [Getting your Camino API token](#getting-your-camino-api-token). Each person must create **their own** token.

```sh
git clone https://github.com/carlosceja27/camino-mcp.git
cd camino-mcp
uv sync --locked
# Launches the MCP stdio server; your MCP client normally starts this for you:
uv run --locked camino-mcp
```

## Getting your Camino API token

1. Sign in at <https://camino.instructure.com> with your SCU account.
2. In the left global navigation bar, click **Account** (your profile picture), then **Settings**.
3. Scroll to **Approved Integrations** and click **+ New Access Token**.
4. For **Purpose**, enter something recognizable, such as `Camino MCP (local)`.
5. Set an **Expiration date** — a short window such as the current term or less is recommended. Leaving it blank creates a token that does not expire.
6. Click **Generate Token**.
7. **Copy the token immediately.** Canvas shows the full token only once; after you close the dialog, you would need to regenerate it.
8. Store it privately and supply it as `CAMINO_API_TOKEN` (see below).

To revoke a token later, return to **Account → Settings → Approved Integrations**, click **Details** beside the token, then **Delete**. Do this if the token is ever exposed or no longer needed.

If you don't see **+ New Access Token**, or Camino says you are not authorized to create tokens, your institution may have disabled user-generated tokens. Contact SCU Technology Help; this server cannot work around that restriction.

The token acts as **you**: anyone with it can read your Camino courses, messages, and grades and use any other access your account has in Canvas. Treat it like a password.

### Note for AI assistants helping a user set this up

If a tool returns `CAMINO_API_TOKEN is not set` or `Camino rejected the API token`, walk the user through the steps above, one step at a time and in plain language. Ask which AI app and operating system they use, then point them to the matching section under [Local AI clients](#local-ai-clients). After they restart the app, call `check_setup` to confirm it works. **Never ask the user to paste their token into the chat**, and never write it into repository files, shared configs, command-line arguments, or logs. Instead, direct them to enter it themselves using one of the private methods below (for example, `read -r -s CAMINO_API_TOKEN; export CAMINO_API_TOKEN` in a terminal, or their MCP client's private environment settings), then restart the MCP client so the server picks it up. If the user already pasted a token into a chat, recommend revoking it and generating a new one.

## Supplying the token

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

In Claude Desktop open **Settings → Developer → Edit Config**. This opens your private `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`). Add:

```json
{
  "mcpServers": {
    "camino": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/camino-mcp", "camino-mcp"],
      "env": {"CAMINO_API_TOKEN": "paste-your-token-here"}
    }
  }
}
```

Desktop-launched apps usually do **not** inherit shell exports, so the `env` entry is the simplest option. That file lives only in your user account; never share, sync, or commit it, and revoke the token if the file is exposed. Fully quit and reopen Claude Desktop, then ask *"Check my Camino setup."* Claude Desktop local MCP servers run on your machine (unlike its web connectors). Each client has its own config path and support level. [Claude local MCP help](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

## Browser-based ChatGPT, Gemini, and Claude

| Browser product | What it expects | Can this repository be uploaded or pasted directly? |
| --- | --- | --- |
| [ChatGPT web MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) | An accessible **remote MCP endpoint** and eligible account/workspace features; OpenAI documents Secure MCP Tunnel for supported products. | **No.** A local stdio process is not a remote endpoint. |
| [Gemini web custom apps](https://support.google.com/gemini/answer/17209137?hl=en) | An MCP **server URL**; access is subject to Google's account, region, language, and feature requirements. | **No.** A GitHub clone/stdio command is not a URL for an MCP service. |
| [Claude web custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) | A reachable **remote MCP URL** from Anthropic's cloud, subject to plan and workspace rules. | **No.** Claude web cannot launch your local process. |

**This project does not implement a remote transport, OAuth, user isolation, or a hosted endpoint.** To use a browser product, *you* would need to deploy and secure a compatible remote MCP service (or a supported user-controlled tunnel/bridge where documented), with appropriate HTTPS, access control, per-user authentication, and institutional approval. Do **not** simply expose this stdio server or place a shared Camino token in an unauthenticated public wrapper. We do not provide or operate such a service, and we do not claim these browser paths are tested with this project. A self-hosted bridge also changes the privacy and maintenance model; local clients are the supported path here.

### Local models (Ollama, LM Studio, etc.)

Any local stdio MCP client works. For small models: IDs may be sent as numbers or strings, all tools return short JSON with `complete`/`error`, and the server sends usage instructions during MCP initialization. Models with at least 7–8B parameters and native tool calling (for example Qwen 2.5/3, Llama 3.1+) work best. If a model loops or picks the wrong tool, ask directly: *"Use the upcoming tool."*

## Things to ask

- "Check my Camino setup." · "What courses am I in?"
- "What's due in the next 3 days?" · "Do I have anything overdue?"
- "What are my grades?" · "Show the instructions for the Week 2 homework in Career Communication."
- "Any new announcements in Political Philosophy?" · "Download the syllabus PDF to ~/Downloads."

## Tools and behavior

- `check_setup`: verifies the token by reading your own Camino profile name; use it after setup.
- `list_courses`: merges paginated active, invited/pending, and favorite courses, deduplicated by numeric ID; **unstarred courses stay included**. Includes the term name and course end date when available. Archived active enrollments may appear.
- `list_assignments(course_id, bucket?)`: accepts a numeric course ID (number or string) and requests submission metadata. Supported Canvas buckets: `future`, `past`, `overdue`, `upcoming`, `unsubmitted`, `ungraded`, `undated`.
- `upcoming(days=7)`: scans active courses for dated assignments due within the next 1–31 rolling 24-hour days that are not submitted or excused.
- `overdue(include_ended_courses=false)`: past-due work you have not turned in on Camino. It leaves out paper/in-class/no-submission items (unless Canvas marks them missing), excused work, and courses whose end date has passed. Set `include_ended_courses=true` to include those courses.
- `grades`: current enrollment grade/score, **when Canvas exposes it**; not a grade transcript.
- `get_assignment(course_id, assignment_id)`: full assignment HTML instructions/description and submission information.
- `list_pages(course_id)` / `get_page(course_id, page_url)`: course page index and full page HTML body. `page_url` is the slug from `list_pages`, not a full URL.
- `list_discussions(course_id)` / `get_discussion(course_id, topic_id)`: discussion topics and initial topic message; replies are not included.
- `list_announcements(course_id)`: course announcements, including message bodies.
- `list_conversations(course_id)` / `get_conversation(conversation_id)`: Canvas Inbox threads filtered by course, then full messages for a selected thread. The detail call accepts a conversation ID accessible to the token; it is not course-scoped.
- `list_files(course_id)` / `download_file(course_id, file_id, destination_dir)`: inspect course file IDs and download a selected file to an **existing absolute directory** on the machine running the MCP server. No overwrites; 20 MB maximum; filename and downloaded size checked against Canvas metadata. The Canvas-managed signed CDN chain is followed at most three hops without forwarding the bearer token; any other host fails. The file is saved locally, not sent as an MCP attachment or uploaded to the model.

Cross-course scans skip courses you can't access (for example unpublished) and return them in `skipped_courses` with `"complete": false`; any other failure, such as a Camino outage, stops the scan with an error. No partial result is labeled complete. Successful tool responses include `"complete": true`; errors include `"complete": false`. Course content HTML is returned as data, not executed or treated as instructions. List responses omit arbitrary Canvas fields and signed file URLs. Only Camino HTTPS links are emitted in assignment summaries. Undated/invalid-date work is omitted from date-window tools; use `list_assignments` to inspect it. Dates are compared as timezone-aware instants.

## Security and limitations

- API calls are limited to Camino HTTPS; file downloads allow only a Canvas-hosted redirect to `*.canvas-user-content.com` and never forward credentials to that CDN. No arbitrary URL fetches. Pagination is restricted to the same endpoint. Requests time out; rate-limited responses (429, or Canvas's 403 "Rate Limit Exceeded") get two short retries; pagination is capped at 20 pages and fails rather than silently truncating results.
- **Read-only means no Canvas writes**; `download_file` does write one new local file in the requested directory. Your AI client may still transmit returned content to its model provider. Use only a trusted client and handle student information under applicable institutional rules.
- Automated tests use synthetic Canvas responses. A live Camino smoke test checked representative read endpoints and a redirect, but course-specific permissions, availability, file types, and Inbox content vary. Some courses return 404 for Pages when that feature is unavailable; other Canvas file CDNs may be rejected by the strict allowlist.
- Do not paste tokens or full private tool responses into public bug reports.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `CAMINO_API_TOKEN is not set` | The AI app isn't passing your token. Add it to that app's MCP settings (see your client above) and fully restart the app. |
| `Camino rejected the API token` | The token expired, was deleted, or was copied incompletely. Create a new one and replace the old value. |
| Camino tools don't appear at all | Check that the `uv` and project paths in the config are **absolute** and correct (`command -v uv`), then restart. Run `uv run --locked camino-mcp` in the project folder to see startup errors (press Ctrl+C to stop). |
| `skipped_courses` in results | Those courses aren't published or accessible to you yet; everything else is still listed. |
| `rate-limiting` | Wait a minute and ask again. |
| `Could not reach Camino` | Check your internet connection or whether Camino is down. |
| An assignment seems missing from `overdue` | Paper/in-class items, excused work, and ended courses are left out. Ask for `list_assignments` for that course, or `overdue` with ended courses included. |

## Development

```sh
uv sync --extra dev --locked
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked pytest -q --cov=camino_mcp --cov-report=term-missing
uv build --no-sources
```

The suite uses synthetic Canvas responses and an offline MCP stdio handshake. Contributions welcome; please include tests, and do not submit real coursework or tokens. The repository is distributed under [Apache License 2.0](LICENSE). The separate Camino Assistant skill inspired this implementation but is not bundled here.
