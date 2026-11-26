# Sunrise for Home Assistant

A skills harness for Home Assistant: agent skills that work on any setup, memory that makes them
yours, a guided and safe way to build your own, and a set of tools that help any agent (Claude Code, Codex, Cursor,
Claude Desktop, ChatGPT, or Home Assistant's own Assist) organize and look after your home.

It works out of the box, and you can change every part of it. It's free and open source (MIT).

- **Agent-agnostic.** You bring the agent. It reaches your house through Home Assistant's own
  MCP Server.
- **Local by default.** The integration makes no internet calls: no telemetry, no update checks,
  no cloud services. Your agent runs on a device on your home Wi-Fi and talks to Home Assistant over
  your home network.
- **Safe by rule.** Its tools never touch the router, Wi-Fi or passwords; a skill may read or change
  the router only after you sign in yourself and say yes to each change. It never locks, unlocks or
  opens anything without your yes. It takes a local checkpoint before a change, and every change can be undone.
- **Judged by you.** A skill run counts as a success only if it worked *and* a non-technical
  person would be happy with how it went ([the rubric](skills/_shared/RUBRIC.md)).

## What's inside

| Skill | Use it when | Needs the internet? |
|---|---|---|
| `welcome` | right after install, or "get started": learns the house, makes one routine with you to show how asking works, then looks for what would help most if you want; asks "keep going, or stop here?" after each step and picks up where you stopped | only if an idea in the last step uses a cloud service |
| `learn-the-house` | first run, or "get to know my house": reads Home Assistant, asks at most five questions, fills memory, shows what it now knows | no |
| `add-a-device` | "I bought a new light": identifies it, gives you the pairing steps, names it, puts it in its room, tests it | only to look up the device |
| `routines` | "do X when Y": restates it, checks it, saves it, runs it once to test, puts things back; change or remove one the same way | no |
| `device-diagnosis` | a device can't be reached, is flaky, slow or wrong: finds the failing layer, fixes what software can, and looks at the hardware if you allow a camera or send a photo | only to look up the device |
| `wifi-diagnosis` | devices keep dropping or won't come back: measures, reads the router with you signed in, fixes in order | only to look up your router and devices |
| `improve-home` | "how could my home be smarter?": at most five ideas, each with evidence from your house; builds the ones you pick; never pitches the same idea twice | only for ideas that use a cloud service |
| `custom-cards` | "make me a dashboard", "add a card for the lights": the house's own dashboards from a card library in its look, catalog first, stock dashboards untouched; tested, checked on a real device, undoable | only to install the build tools the first time |
| `undo` | "what did you change?", "put it back": lists recent changes and undoes them, smallest step first | no |
| `build-a-skill` | "make this repeatable": builds a skill from a request or from work just done, your way, tested | no |

**Building blocks.** The tools are the shared primitives: map the house, act with read-back,
diagnose, routines, checkpoint, undo, memory. The skills are repeatable jobs built on them. A
bigger request chains skills, each finishing its own check before the next starts
(`add-a-device` then `routines`; `device-diagnosis` then `wifi-diagnosis`). A handoff is one
line in a skill naming the other skill and when; there is nothing else to configure.

**Checkpoints are local.** Before a change that can't be undone in one step, Sunrise makes a
Home Assistant backup on this machine only. Nothing is sent anywhere.

`skills/_shared/HOUSE-BASICS.md` is the reference every skill follows: find, act, read back.
Without the internet a skill says what it can't look up and carries on with what it can do.

**Skills are general; your house is in memory.** A skill holds the method. What it learns about
your home (your router's pages, how your bulbs behave, which device to test on, how you like
things reported) goes into memory files, so the next run starts from there.

### Memory

Plain Markdown in `<config>/sunrise/memory/` that the agent writes and you can open, edit or delete:
`owner.md`, `house.md`, `playbooks/<thing>.md`, `log.md`. In Home Assistant it shows as
`sensor.sunrise_memory` (the number of files, with each file's name, first line and when it changed).

- Every write and delete is one git commit with who, when and why, and can be put back.
- Passwords, keys and tokens are refused. Files stay inside the folder, are `.md` only and are size-capped.
- The agent sees the list of files at the start of every session and is told to treat them as dated claims.

### Tools

Served as the **Sunrise** API: `house_map`, `act` (does it, then reads it back: CHECKED / NOT
CONFIRMED / UNREACHABLE), `audit`, `diagnose_device`, `fix_device`, `registry_edit`, `routine`
(automations: check, save, try, delete), `changes`, `undo`, `backup` (a local checkpoint),
`network_check`, `usage`, `list_skills`, `get_skill`, `skill_update`, `memory_list`, `memory_read`,
`memory_write`, `memory_delete`, `behavior_log`, `behavior_revert`, `log_run`. Each declares honest
read-only / destructive annotations. The API's prompt (the MCP prompt "Sunrise") carries the fixed
rules, the skills index and the memory index.

Your skills live in `<config>/sunrise/skills/`, outside `custom_components`, so updates never
overwrite them. If you or your agent edit a built-in skill, it's yours: a product update never
replaces it.

### Your agent's behavior is a git repository you can read

`<config>/sunrise/` is a plain git repository. It tracks two things only: `skills/` and `memory/`.
Every change the agent makes to either is one commit, with its reason as the message and `agent`,
`user` or `product` as the author. Edits you make by hand are committed as yours the next time
Sunrise touches the folder.

```bash
cd /config/sunrise        # wherever your Home Assistant config lives
git log --oneline         # what changed, newest first
git show <commit>         # exactly what one change did
```

- Ask the agent "what did you change?" and it reads the same history (`behavior_log`); "put it
  back" makes a new commit that reverses one (`behavior_revert`). History is never rewritten.
- The repository has no remote. Nothing fetches or pushes; it never leaves the machine.
- Run data, logs and anything else in the folder are ignored, and memory refuses secrets, so
  there are no passwords in the history.
- It covers the agent's behavior, not the house. Renames, room moves and routines go back with
  `undo`; a checkpoint (a local Home Assistant backup) is the way back when everything is broken.
- It uses the `git` program that Home Assistant's own images include. On a hand-made install
  without git, Sunrise says so at setup instead of running without history.

## Install

Requires Home Assistant 2026.10 or newer. Works on Home Assistant OS and Container installs alike:
no add-on, no Docker changes, no token for the integration itself. There are two ways in.

### 1. Let Claude Code install it (the plugin)

```bash
claude plugin marketplace add quantumquadtrees8523/sunrise
claude plugin install connect-to-box@sunrise
claude plugin install sunrise@sunrise
```

or, inside Claude Code on version 2.1.275 or later:

```
/plugin install connect-to-box --marketplace quantumquadtrees8523/sunrise
/plugin install sunrise --marketplace quantumquadtrees8523/sunrise
```

Then run `/sunrise:install`. It first runs `/connect-to-box:connect-to-box` to find the box and
get a key-based shell on it, then backs up Home Assistant, installs HACS if it's missing, adds
Sunrise, connects Claude Code over MCP and checks it on a device you pick. You do a few things
yourself, each in a prompt Claude opens for you: copy your SSH key to the box if it isn't there,
store a Home Assistant token when the box needs one, accept HACS's terms and authorize it with
GitHub, and choose the test device. You can also run `/connect-to-box:connect-to-box` on its own
whenever you need a shell on the box.

Both plugins live in [`claude-plugins/`](claude-plugins/) and run on the Claude side only. Neither
is part of what HACS installs (`custom_components/sunrise/`) or of the house skills in `skills/`,
which ship to the box.

### 2. By yourself

**HACS (custom repository):** HACS → ⋮ → Custom repositories → add
`https://github.com/quantumquadtrees8523/sunrise`, type "Integration" → download "Sunrise" →
restart Home Assistant.

**By hand:** copy `custom_components/sunrise/` into your `<config>/custom_components/` and
restart Home Assistant.

Then: Settings → Devices & services → Add integration → **Sunrise** → Submit.

## Point your agent at it

1. Settings → Devices & services → Add integration → **Model Context Protocol Server**. Select
   "Sunrise" (you can select Assist too).
2. Your agent connects to `http://<your-home-assistant>:8123/api/mcp/sunrise`. This endpoint
   needs an administrator: create a long-lived access token (your profile → Security), or use Home
   Assistant's sign-in if your MCP client supports it.

Claude Code, signing in to Home Assistant in the browser (needs an `https://` address for Home Assistant):

```bash
claude mcp add --transport http sunrise https://<your-home-assistant>/api/mcp/sunrise
```

then `/mcp` → `sunrise` → Authenticate. Or with a token, on the home network:

```bash
claude mcp add --transport http sunrise \
  http://homeassistant.local:8123/api/mcp/sunrise --header "Authorization: Bearer $HA_TOKEN"
```

Any client that speaks MCP over Streamable HTTP works the same way.
A client that only speaks stdio (some desktop apps) can use a local bridge such as `mcp-remote`.

## Skills without the integration

Each skill is a standalone [Agent Skills](https://agentskills.io) folder (`SKILL.md` with `name`
and `description`, plus its `references/`). Install them into a coding agent with:

```bash
npx skills add quantumquadtrees8523/sunrise                       # all of them
npx skills add quantumquadtrees8523/sunrise --skill build-a-skill
```

Without the integration's tools, the skills tell the agent to use what it has (Home Assistant's
own MCP tools, ha-mcp, the REST API) and keep every rule.

## Fully offline (an option)

Everything above works on the home network alone. If you also want the model local:

- **Home Assistant's own agent:** add the Ollama integration, pick a model that supports tools,
  and in its options under "Control Home Assistant" select **Sunrise** (and Assist). Assist
  then uses these tools and the rules prompt. Small local models follow long skills less reliably.
- **A coding agent on a local model:** run a coding agent that supports local models through
  Ollama or LM Studio, with the MCP server above.

## Later: an opt-in cloud mode

There's one marked seam for a future paid tier (background and proactive work, remote access
through a relay): `custom_components/sunrise/cloud.py`. It's off by default, nothing turns
it on in this version, and it never connects. A test checks that.

## Develop

```bash
uv venv -p 3.14 .venv && . .venv/bin/activate && uv pip install -r requirements-test.txt
python3 scripts/sync_skills.py       # after editing skills/: copies into references/ and the integration
pytest                                # from this folder
```

Run reports stay on your machine (`<config>/sunrise/runs.jsonl`; `log_run op=export`
writes a copy with names and addresses removed for you to share by hand).
