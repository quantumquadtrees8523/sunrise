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
  opens anything without your yes. It backs up before a change, and every change can be undone.
- **Judged by you.** A skill run counts as a success only if it worked *and* a non-technical
  person would be happy with how it went ([the rubric](skills/_shared/RUBRIC.md)).

## What's inside

| Skill | Use it when | Needs the internet? |
|---|---|---|
| `build-a-skill` | "make this repeatable": builds a skill from a request or from work just done, your way, tested and backed up | no |
| `device-diagnosis` | a device can't be reached, is flaky, slow or wrong: finds the failing layer (power, network, the maker's service, the device, Home Assistant), fixes what software can, and looks at the hardware if you allow a camera or send a photo | only to look up the device |
| `wifi-diagnosis` | devices keep dropping or won't come back: measures, reads the router with you signed in, fixes in order. `device-diagnosis` hands over to it when the evidence says Wi-Fi | only to look up your router and devices |
| `improve-home` | "how could my home be smarter?": at most five ideas, each with evidence from your house; builds the ones you pick, tested and undoable; never pitches the same idea twice | only for ideas that use a cloud service |

`skills/_shared/HOUSE-BASICS.md` is the reference every skill follows: find, act, read back.
Without the internet a skill says what it can't look up and carries on with what it can do.

**Skills are general; your house is in memory.** A skill holds the method. What it learns about
your home (your router's pages, how your bulbs behave, which device to test on, how you like
things reported) goes into memory files, so the next run starts from there.

### Memory

Plain Markdown in `<config>/sunrise/memory/` that the agent writes and you can open, edit or delete:
`owner.md`, `house.md`, `playbooks/<thing>.md`, `log.md`. In Home Assistant it shows as
`sensor.sunrise_memory` (the number of files, with each file's name, first line and when it changed).

- Every write and delete is checkpointed with who, when and why, and can be reverted.
- Passwords, keys and tokens are refused. Files stay inside the folder, are `.md` only and are size-capped.
- The agent sees the list of files at the start of every session and is told to treat them as dated claims.

### Tools

Served as the **Sunrise** API: `house_map`, `act` (does it, then reads it back: CHECKED / NOT
CONFIRMED / UNREACHABLE), `audit`, `profile_get`, `profile_update`, `diagnose_device`, `fix_device`,
`registry_edit`, `undo`, `backup`, `network_check`, `usage`, `suggestions`, `list_skills`,
`get_skill`, `skill_update`, `skill_history`, `skill_revert`, `memory_list`, `memory_read`,
`memory_write`, `memory_delete`, `memory_history`, `memory_revert`, `log_run`. Each declares honest
read-only / destructive annotations. The API's prompt (the MCP prompt "Sunrise") carries the fixed
rules, the skills index and the memory index.

Your skills live in `<config>/sunrise/skills/`, outside `custom_components`, so updates never
overwrite them. Every change to a skill is checkpointed (version, time, who, why, diff) and can be
reverted. If you or your agent edit a built-in skill, it's yours: a product update never replaces it.

## Install

Requires Home Assistant 2026.10 or newer. Works on Home Assistant OS and Container installs alike:
no add-on, no Docker changes, no token for the integration itself. There are two ways in.

### 1. Let Claude Code install it (the plugin)

```bash
claude plugin marketplace add quantumquadtrees8523/sunrise
claude plugin install sunrise@sunrise
```

or, inside Claude Code on version 2.1.275 or later:

```
/plugin install sunrise --marketplace quantumquadtrees8523/sunrise
```

Then run `/sunrise:fresh-install`. It backs up Home Assistant, installs HACS if it's missing, adds
Sunrise, connects Claude Code over MCP and checks it on a device you pick. You do three things
yourself: authorize HACS with GitHub, sign in to Home Assistant, and choose the test device.

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
