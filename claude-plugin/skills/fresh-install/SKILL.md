---
name: fresh-install
description: "Fresh-install the Sunrise HACS integration on a Home Assistant box from Claude Code: back up, install HACS, add Sunrise, connect over MCP, verify on a real device."
---

# Sunrise fresh install

Installs Sunrise (`https://github.com/quantumquadtrees8523/sunrise`, a Home Assistant custom integration that serves tools and skills over HA's MCP Server) the way a new user would: through HACS, on a box that has neither. Run it from Claude Code on a machine that can reach the box. Every run doubles as a test of the install experience, so record every snag.

This skill lives on the Claude side: Sunrise's own skills sit behind HA's MCP server and can't be seen until this install is done.

## Stance
Act as the implementation specialist. Do every step you can yourself, and stop only for the steps that need the owner. Those are listed under "Owner steps", with the exact wording to use.

## Hard rules
- Take a checkpoint before the first change: a Home Assistant backup kept on the box only (no cloud location). Confirm it's listed.
- Never type, print or store passwords, tokens or the GitHub device code's result. Never print env files.
- One change, then check it. Don't upgrade Home Assistant as a side effect; if a minimum version blocks the install, stop and say so.
- If something is already installed (HACS, Sunrise), don't reinstall over it. Report what's there and continue from the first missing step.
- Live device tests use one test device chosen in Phase 0, never a hardcoded one. Read the result back from the device or HA state, and put the device back the way it was found.

## Phase 0: reach the box and take stock
1. Get a shell on the box: SSH on the home network (ask the owner for the address and user if you don't have them), or Home Assistant's own Terminal app on an OS install.
2. Record:
   - the install type (OS, or Container: `docker ps`)
   - the HA config path and HA version (`.HA_VERSION`)
   - what's in `custom_components/`
   - whether the Model Context Protocol Server integration is set up
3. Check Sunrise's minimum HA version (`hacs.json` → `homeassistant`) against the box.
4. Check whether this HA version ships HACS built in (newer releases include it as the Marketplace). If it does, skip Phase 2's download.

5. Choose the test device:
   - If `memory/box.md` names one, use it.
   - Otherwise list the lights and switches that are reachable right now, and ask the owner once: "Which one can I switch off and on to test? Pick something harmless that you can see."
   - Never pick a lock, garage door, alarm, heater or anything safety-related.
   - If the house has nothing switchable, verify read-only (`house_map` matches HA's states) and say the live test was skipped.
   - Save the choice to `memory/box.md`, and once Sunrise is connected, to its `house.md` with `memory_write`.

**Exit:** a shell, the config path, the versions, a list of what's already installed, and a test device (or a note that there is none).

## Phase 1: back up
Create a local HA backup (Settings → System → Backups, with only the local location selected, or the `backup.create` action), named `before-sunrise-<date>`. Confirm it's listed.

## Phase 2: HACS
1. Install HACS's files with its official script, run where HA's config is:
   - OS: in the Terminal app, `wget -O - https://get.hacs.xyz | bash -`
   - Container: `docker exec <ha-container> bash -c "wget -O - https://get.hacs.xyz | bash -"`

   Read the script's output. It must end with HACS in `custom_components/hacs`.
2. Restart Home Assistant and wait until it's healthy. Check the log for HACS errors.
3. **Owner step:** add the HACS integration and authorize it with GitHub (below).

**Exit:** HACS appears in the sidebar and shows repositories.

## Phase 3: Sunrise
1. In HACS, open the ⋮ menu → Custom repositories. Add `https://github.com/quantumquadtrees8523/sunrise` with type Integration. In a browser session you control, do this yourself; otherwise it's an owner step.
2. Download "Sunrise" in HACS. Confirm `custom_components/sunrise/manifest.json` exists, and note its version.
3. Restart Home Assistant and wait until it's healthy. Check the log for `sunrise` errors.
4. Go to Settings → Devices & services → Add integration → **Sunrise** → Submit.
5. In the Model Context Protocol Server integration (add it if it's missing), make sure the Sunrise tool set is exposed.

**Exit:** the Sunrise entry is loaded with no errors, and `<config>/sunrise/` exists.

## Phase 4: connect Claude Code
- Endpoint: `/api/mcp/sunrise` on the box's **HTTPS** address (Claude Code requires HTTPS).
  ```
  claude mcp add --transport http sunrise https://<ha-address>/api/mcp/sunrise
  ```
  Then `/mcp` → `sunrise` → Authenticate (the owner signs in to HA in the browser).
- Fallback: a long-lived token the owner creates, passed with `--header "Authorization: Bearer $HA_TOKEN"` from an environment variable the owner sets.

**Exit:** `/mcp` shows `sunrise` connected and lists its tools.

## Phase 5: verify
Report pass or fail for each:
- [ ] the backup is listed
- [ ] HACS is loaded, with Sunrise shown as installed at the expected version
- [ ] the Sunrise config entry is loaded, with the log clean
- [ ] the MCP tool list includes Sunrise's tools (`house_map`, `act`, `routine`, `changes`, `list_skills`, `memory_list`, …)
- [ ] `list_skills` returns every skill in the repo's `skills/` folder (compare with the README's table), each readable with `get_skill`
- [ ] `memory_list` answers, and `sensor.sunrise_memory` exists in Home Assistant
- [ ] `act` turns the test device off, then on, each returning CHECKED and confirmed by a direct read
- [ ] nothing else changed: the other integrations are still loaded

## Owner steps (say these exactly, one at a time)
- **HACS + GitHub:** "In Home Assistant: Settings → Devices & services → Add integration → HACS. Tick the acknowledgements, then open the GitHub link it shows, enter the code, and approve. Tell me when it says success."
- **MCP sign-in:** "In Claude Code run `/mcp`, pick `sunrise`, choose Authenticate, and sign in to Home Assistant in the browser window."
- **Token (fallback only):** "Profile → Security → Long-lived access tokens → Create, name it 'Claude', and set it yourself with `export HA_TOKEN=…` in your terminal. Don't paste it to me."

## Rollback
Remove the Sunrise integration entry → remove Sunrise in HACS → restart. Data stays in `<config>/sunrise/` until deleted. If something is badly wrong, restore the Phase 1 backup.

## Report and memory
Report:
- the checklist
- the versions (HA, HACS, Sunrise)
- each owner step taken and how long the whole install took
- **every snag a new user would hit**, as a list (this is the product feedback)

If `memory/` beside this skill is writable, add a dated entry to `memory/log.md` with the same, and keep `memory/box.md` current. No secrets.