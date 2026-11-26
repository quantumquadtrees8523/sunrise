---
name: install
description: "Install Sunrise (a Home Assistant custom integration that serves tools and skills over HA's MCP Server) on a Home Assistant box: connect via connect-to-box, checkpoint, HACS or Marketplace, the Sunrise integration, connect Claude Code over MCP, verify on a real device."
---

# Sunrise install

Installs Sunrise (`https://github.com/quantumquadtrees8523/sunrise`) the way
a new user would, running from Claude Code on a machine that can reach the
box. Every run doubles as a test of the install experience, so record every
snag.

This skill runs on the Claude side. Sunrise's own skills sit behind HA's MCP
server, and you can't see them until this install is done.

**Getting onto the box is not this skill's job.** It belongs to
`connect-to-box:connect-to-box`, which this skill invokes first (Phase 0).
Everything about discovery, the access ladder, the box record, secrets,
restart readiness, and HTTPS/CA/OAuth checks lives there. Don't duplicate it
here.

## Stance

Act as the implementation specialist. Do every step you can yourself, and stop
only for the steps that need the owner. **Real boxes are in dirty states.**
Work out what you're dealing with before you change anything, and when the
obvious route is closed, keep going another way.

**Meet the owner where their box is.** Never propose rebuilding, reimaging or
starting clean to make the install easier. If a route is blocked, find another
one. A fresh install is only ever a last resort the owner raises.

**Explain as you go.** When a term may be new to the owner (HACS, MCP, a
token, a certificate), explain it in one plain sentence, and tell them they can
say **explain <term>** (`/sunrise:explain`) for more. After an explanation,
pick up at the same step.

## Hard rules

- Take a checkpoint before the first change. Keep it **on the box only**, with
  no cloud location, and confirm it exists.
- **Never type, print or store passwords or tokens.** (See connect-to-box →
  *Secrets*. Use `box-secret`, the owner stores, you reference.)
- **Never guess usernames.** Ask.
- One change, then check it. Don't upgrade Home Assistant as a side effect. If
  a minimum version blocks the install, stop and say so.
- If something is already installed (HACS, Sunrise), don't reinstall over it.
  Report what's there and continue from the first missing step.
- Live device tests use one test device chosen in Phase 0, never a hardcoded
  one. Read the result back from HA, and put the device back exactly as you
  found it.
- **Run owner commands in the visible terminal panel** so you can read the
  result. Don't take "done" on trust.

## Where things go

- **Box facts** (shell, paths, containers, HTTPS, baseline, test device) go in
  connect-to-box's record:
  `~/.claude/connect-to-box/boxes/<box-slug>/box.md`. Append as you go,
  failures included.
- **Install log** (one dated entry per run: checklist, versions, owner steps,
  snags) goes in `~/.claude/connect-to-box/boxes/<box-slug>/sunrise-install-log.md`.
- **On the box**, once Sunrise is connected: write `box.md` and `house.md`
  with `memory_write` so Sunrise itself knows.

Secret *names* only, never values, in any of them.

Two helpers ship with the skills. Neither is on the `PATH`:
- `box-secret` is in connect-to-box's `scripts/` folder. Everywhere this file
  says `box-secret`, use its full path. It still finds secrets the older
  `sunrise-secret` stored.
- `scripts/ha_ws.py` beside this file is an HA websocket client that runs
  *inside* the HA container and reads the token from stdin.

---

## Phase 0: connect (invoke `connect-to-box:connect-to-box`)

Invoke the **`connect-to-box:connect-to-box`** skill and follow it through
**Phases A–D**, with `MCP_PATH=/api/mcp/sunrise` for the HTTPS/MCP checks.
Don't continue until its output contract is satisfied and in the box record:
a working shell command, install type, config path, HA container name, write
path, HA version, and the HTTPS base with OAuth and CA verdicts.

If a record already exists with a working shell, connect-to-box starts from
there, and this phase takes one command.

### 0b: Sunrise-specific stock-take

1. **Version gate.** Read Sunrise's minimum from the repo's `hacs.json` →
   `homeassistant`. Compare it with the HA version from the box record (from
   mDNS). The version decides Phase 2's path:
   - below the minimum: **stop**, and see *If the version is wrong*.
   - minimum up to 2026.10: legacy HACS script.
   - 2026.11+: Marketplace (HACS is built in, and the script no longer works).
2. Record what's in `custom_components/`, and whether HACS, Sunrise and the
   **Model Context Protocol Server** integration are set up (read
   `.storage/core.config_entries` through the container, domains only).
3. **Snapshot pre-existing breakage before you touch anything.** Record every
   open repair and every error/warning *category* in the log in the box
   record's *Baseline* block. At the end you'll be asked whether you broke
   anything, and without this you can't answer honestly. A box with two
   failing automations before you start must still have exactly those two at
   the end.
   ```
   docker exec <ha> python3 -c "import json;d=json.load(open('/config/.storage/repairs.issue_registry'))
   [print(i['domain'],i['issue_id']) for i in d['data']['issues'] if not i.get('dismissed_version')]"
   grep -E '^[0-9-]+ [0-9:.]+ (ERROR|WARNING)' <config>/home-assistant.log \
     | sed -E 's/^[0-9-]+ [0-9:.]+ (ERROR|WARNING) \([^)]*\) \[([^]]+)\].*/\1 \2/' | sort | uniq -c | sort -rn
   ```
4. **Backup agents.** Read `.storage/backup` through the container and print
   **only** `create_backup.agent_ids`. It also holds the backup password. If
   the defaults include a cloud agent (for example `cloud.cloud`), a default
   `backup.create` would upload, so don't fire it (see Phase 1).
5. **Classify every snag from here on:**
   - *generalizable*: anyone installing Sunrise would hit it. It goes in the
     report as product feedback.
   - *box-specific*: this owner's particular mess. Note it, help if it's
     cheap, but don't harden the installer against it.

   Reverse proxies, custom DNS, tunnels and leftover services are usually
   box-specific. Version gates, missing steps, wrong ordering and API quirks
   are generalizable.

### 0c: choose the test device

- If the box record names one, use it.
- Otherwise list the lights and switches that are available right now, and
  ask once: "Which one can I switch off and on to test? Pick something
  harmless that you can see." Suggest one that is on and one that is off.
- Never a lock, garage door, alarm, heater or anything safety-related.
- If nothing is switchable, verify read-only (`house_map` matches HA's states)
  and say you skipped the live test.
- Record its **exact** prior state (state, brightness, colour temp/mode) in
  the box record.

### 0d: decide the route, and say it up front

If connect-to-box reported **OAuth can't work** (protected-resource 404, no
issuer, or a localhost issuer), Claude needs a long-lived token at the end
anyway. **Get it now and use it for the whole install.** With the token, you
can run every HA-side step over the API, and the owner's only remaining steps
are HACS's acknowledgements and the GitHub device code. Without it, steps 1, 2
and 4 of Phase 3 are browser clicks you can't do (driving their browser would
mean entering their HA password), and on a Container install that's three
separate round-trips. Tell the owner this choice before you start, not after.

To get the token, open `box-secret set ha-token` in their terminal panel and
say: *"Home Assistant → your profile → Security → Long-lived access tokens →
Create, name it 'Claude', copy it, and paste it at the prompt. It won't echo,
and I never see it."* Confirm with `box-secret check ha-token` and a `GET
/api/` → 200.

**Tell the owner now that nothing will appear in the HA UI while you work
over the API.** When HACS is set up, they need to **refresh the HA tab** to
see the HACS sidebar item. (In testing, the owner asked "where is the UI? I'm
not seeing anything".)

---

## Phase 1: checkpoint

Prefer an HA backup kept **on the box only** (Settings → System → Backups
with only the local location selected, or `backup/generate` with
`agent_ids: ["backup.local"]`), named `before-sunrise-<date>`. Confirm it's
listed, and confirm it on disk too: `ls -lt <config>/backups | head -3`.

If you can't guarantee the backup stays local (you can't read the agent
config, or the default agents include a cloud agent and you have no token to
pass `agent_ids`), take a plain local snapshot through the container instead:

```
docker exec <ha> tar -czf /config/backups/before-sunrise-$(date +%F-%H%M).tar.gz \
  -C /config --exclude=./backups --exclude='./home-assistant.log*' --exclude=./.cache .
```

Then list its contents to confirm `.storage`, `custom_components`,
`configuration.yaml` and the database are in it. Tell the owner this tarball
**won't appear** in HA's Backups page.

---

## Phase 2: HACS (branch on the HA version)

Home Assistant **2026.11** absorbed HACS as the built-in **Marketplace**, and
**the standalone HACS installer stops working at 2026.11**. Sunrise's floor is
2026.10. So 2026.10 is the only release where the old script path is correct.

### If the version is wrong, don't just upgrade it

You aren't allowed to upgrade HA as a side effect, and on a real box an
upgrade is rarely a single command. First find out who owns the version (the
compose pin, often `${HA_VERSION:-X.Y.Z}`, whether it's a git checkout,
branch deploys, the owner's own tooling, the exact `-f` set; the connect-to-box
record has most of this). Then tell the owner three things and let them
choose:

1. **Downgrades aren't supported.** HA migrates `.storage` on first boot of a
   newer version, so rolling back means restoring a backup, not reverting the
   pin.
2. **Crossing 2026.11 migrates HACS into Marketplace**, one way.
3. Their existing checkpoint may predate this install, so restoring it would
   undo this work too. Take a fresh one that includes it.

### 2026.11 and newer: Marketplace

Nothing to install. HACS is already there, and an existing HACS install is
migrated automatically on first start after the update. Settings →
**Marketplace** → **Add from link** →
`https://github.com/quantumquadtrees8523/sunrise` → owner does the GitHub
device sign-in → Download. Skip to Phase 3 step 3.

### 2026.10 and older: the HACS script (legacy)

1. Run the official script in HA's config dir:
   - OS: in the Terminal add-on, `wget -O - https://get.hacs.xyz | bash -`
   - Container:
     `docker exec -w /config <ha> bash -c "wget -q -O - https://get.hacs.xyz | bash -"`

   `-w /config` matters, because the script installs relative to the working
   directory. Read its `Current version is X, minimum version is Y` line. It
   must end with `custom_components/hacs/manifest.json` present (note the
   version).
2. Restart HA. Use connect-to-box's *two checks that give false positives*:
   wait for a fresh `Home Assistant initialized` line, then check the log for
   HACS errors.
3. Set up the HACS integration.
   - **Token route:**
     1. `POST /api/config/config_entries/flow {"handler":"hacs"}` returns a
        form with four acknowledgements (`acc_logs`, `acc_addons`,
        `acc_untested`, `acc_disable`).
     2. **These are the owner's to accept.** Show what each says, and ask.
     3. Submit them with `true`. The flow returns `progress` /
        `wait_for_device` with a URL and code.
     4. Owner step: *"Open https://github.com/login/device, enter `<code>`,
        approve. It reads public info only, and I never see a GitHub token."*
     5. Then `POST` the flow again with `{}`, which should return
        `create_entry`.
   - **UI route:** owner step, Settings → Devices & services → Add
     integration → HACS → tick the acknowledgements → GitHub device code.
   - Either way, confirm `custom_components.hacs` reaches
     `Stage changed: running` in the log.

**Exit:** HACS (or Marketplace) is present and shows repositories.

---

## Phase 3: Sunrise

1. Add the repository, as type **Integration**. (On the Marketplace path, this
   was Phase 2's Add from link.)
   - **Token route** (websocket; HACS has no REST API for this). Copy
     `scripts/ha_ws.py` to the box and into the container, then pipe the token
     on stdin:
     ```
     scp ha_ws.py <box>:/tmp/ && ssh <box> 'docker cp /tmp/ha_ws.py <ha>:/tmp/ha_ws.py'
     box-secret get ha-token | ssh <box> "docker exec -i <ha> python3 /tmp/ha_ws.py \
       '[{\"type\":\"hacs/repositories/add\",\"repository\":\"quantumquadtrees8523/sunrise\",\"category\":\"integration\"}]'"
     box-secret get ha-token | ssh <box> "docker exec -i <ha> python3 /tmp/ha_ws.py \
       '[{\"type\":\"hacs/repositories/list\"}]' quantumquadtrees8523/sunrise"     # -> its HACS id
     ```
     `hacs/repositories/list` is about **4.9 MB**, over aiohttp's default
     4 MB websocket frame limit. `ha_ws.py` sets `max_msg_size=0`. Any other
     client needs the same.
   - **UI route:** HACS → ⋮ → Custom repositories → add the URL, type
     Integration.
2. Download it.
   - Token route: `hacs/repository/refresh` and then `hacs/repository/download`
     with `{"repository":"<id>"}`.
   - UI route: the Download button.
   - **Sunrise may have no tagged release.** If so, `available_version` is
     empty and HACS installs from the default branch. That's expected, not a
     failure. Note it in the report.
   - Confirm `custom_components/sunrise/manifest.json` exists and note its
     `version`.
3. Restart HA, with readiness per connect-to-box. Check the log for `sunrise`
   errors. Expect one benign `WARNING ... custom integration sunrise which has
   not been tested by Home Assistant`.
4. Add the integration.
   - Token route: `POST /api/config/config_entries/flow
     {"handler":"sunrise"}` → empty form → `POST {}` → `create_entry`, with
     `result.state` `loaded`.
   - UI route: Settings → Devices & services → Add integration → **Sunrise**
     → Submit.
   - Until this config entry exists, the component doesn't load at all, so an
     empty `custom_components.sunrise` log before this step means nothing.
5. Check the Model Context Protocol Server integration (add it if it's
   missing). If its entry has `all_llm_apis: true`, Sunrise is already exposed.

**Exit:** the Sunrise entry is loaded with no errors, and `<config>/sunrise/`
exists, containing `.git`, `skills/` and `skills.json`.

---

## Phase 4: connect Claude Code

The endpoint is `/api/mcp/sunrise` on the HTTPS base from connect-to-box's
Phase D.

1. **Prove it before you register it.** Using the CA root if the CA is private:
   ```
   curl -s --cacert ~/.claude/certs/<box-slug>-root.crt -X POST \
     -H "Authorization: Bearer $(box-secret get ha-token)" -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
     https://<base>/api/mcp/sunrise
   ```
   A 200 with `serverInfo` means transport and auth are fine.
2. **Register it.**
   - OAuth works: run
     `claude mcp add --transport http sunrise https://<base>/api/mcp/sunrise`,
     then the owner runs `/mcp` → `sunrise` → Authenticate.
   - Token route:
     ```
     claude mcp add -s user --transport http sunrise https://<base>/api/mcp/sunrise \
       --header "Authorization: Bearer $(box-secret get ha-token)" >/dev/null 2>&1
     ```
   - **Redirect the output.** `claude mcp add` echoes `Headers: {
     "Authorization": "Bearer …" }` back in full.
   - **Tell the owner that it also stores the token in plain text in
     `~/.claude.json`.** The keychain only protected the moment of entry.
     Anyone who can read that file can use the token.
3. **Private CA:** check with `claude mcp list` with `NODE_EXTRA_CA_CERTS`
   unset (expect `Failed to connect`) and set (expect `Connected`). Then, with
   the owner's OK, persist it per connect-to-box Phase D: shell profile, not
   `settings.json`. The owner restarts Claude, and `/mcp` should show
   `sunrise` connected. A running session can't pick up a new MCP server or
   CA, so until the restart, verify Phase 5 over direct JSON-RPC (`tools/list`,
   `tools/call`) with the same curl.

If the box has no HTTPS address at all, stop and say so. That's a setup step
for the owner, not something to work around.

**Exit:** `/mcp` shows `sunrise` connected and lists its tools. Before the
owner restarts, direct JSON-RPC calls show the same thing.

---

## Phase 5: verify

Report pass or fail for each:

- [ ] the checkpoint exists on the box (listed in HA, or the tarball on disk
      with its contents checked)
- [ ] HACS/Marketplace shows Sunrise installed at the expected version
- [ ] the Sunrise config entry is loaded, with the log clean
- [ ] the MCP tool list includes Sunrise's tools (`house_map`, `act`,
      `routine`, `changes`, `list_skills`, `memory_list`, …)
- [ ] `list_skills` returns every skill in the repo's `skills/` folder
      (compare with the README's table), and each is readable with
      `get_skill`. In zsh, loop over a literal list; `$VAR` doesn't word-split.
- [ ] `memory_list` answers, and `sensor.sunrise_memory` exists in HA
- [ ] `behavior_log` lists the built-in skills' first commit, and the git log
      on the box matches. The repo is root-owned, so read it through the
      container: `docker exec <ha> git -C /config/sunrise log --oneline`, or
      on the host `git -c safe.directory=<config>/sunrise -C <config>/sunrise
      log --oneline`. Expect `Sunrise <version>: built-in skills` and
      `Sunrise starts keeping the agent's behavior in git`.
- [ ] `act` turns the test device off, then on (or on, then off), each
      returning CHECKED and confirmed by a direct read of HA state. Restore
      the exact prior attributes (brightness, colour temperature).
- [ ] **nothing else changed**: compare against the Phase 0b baseline, not
      against a clean box. Expected additions: `homeassistant.loader` warnings
      for hacs and sunrise, and a HACS repair
      **`restart_required_<id>_main`**, which **survives the restart** that
      follows the download. It's stale, not breakage. Report it and tell the
      owner they can dismiss it.
- [ ] `/mcp` in Claude Code shows `sunrise` connected (after the owner's
      restart, if one was needed)

Clean up anything you copied to the box (`/tmp/ha_ws.py` on the host and in
the container).

## Owner steps (say these exactly, one at a time, in the terminal panel where possible)

- **SSH access:** see connect-to-box rung 4.
- **Token:** open `box-secret set ha-token` in their panel. "Profile →
  Security → Long-lived access tokens → Create, name it 'Claude', copy it, and
  paste it at the prompt. It won't echo, and I never see it."
- **HACS acknowledgements:** show all four and ask for a yes.
- **GitHub device code:** "Open https://github.com/login/device, enter
  `<code>`, approve. It reads public info only. The code expires in about 15
  minutes."
- **HACS + GitHub, UI route (legacy):** "Settings → Devices & services → Add
  integration → HACS. Tick the acknowledgements, open the GitHub link, enter
  the code, approve. Tell me when it says success."
- **Marketplace (2026.11+):** "Settings → Marketplace → Add from link, paste
  the Sunrise URL, and complete the GitHub device sign-in."
- **Test device:** pick one from the list you offered.
- **MCP sign-in (OAuth route only):** "In Claude Code run `/mcp`, pick
  `sunrise`, choose Authenticate, and sign in to Home Assistant."
- **CA trust:** approve adding `NODE_EXTRA_CA_CERTS` to their shell profile,
  then fully quit and reopen Claude.
- **Refresh the HA tab** to see HACS in the sidebar.

## After a pass

Say it worked in one line, then ask once: "Set up your home now?" (default:
yes). Yes: go straight into Sunrise's `welcome` (`get_skill` name=welcome over
the new MCP connection) and follow it from its phase 1, which picks up
wherever memory says onboarding got to. No: "Say **get started** any
time and I'll walk you through it." That is the only question here; don't ask
it twice or start `welcome` without the yes.

## Rollback

Remove the Sunrise integration entry → remove Sunrise in HACS/Marketplace →
restart. Data stays in `<config>/sunrise/` until deleted. Remove the MCP
server with `claude mcp remove sunrise -s user`, and rotate the token. If
something is badly wrong, restore the Phase 1 checkpoint.

## Report

- the checklist
- the versions (HA, HACS/Marketplace, Sunrise, and whether Sunrise came from a
  release or the default branch)
- each owner step taken, and how long the install took
- **every snag, split into generalizable and box-specific.** That split is
  the useful part.
- which connect-to-box rung worked, and which failed

Add a dated entry to `sunrise-install-log.md` beside the box record with the
same content. Make sure `box.md` is complete and answer-first. Then tell the
owner where the record is and what the shell command is.
