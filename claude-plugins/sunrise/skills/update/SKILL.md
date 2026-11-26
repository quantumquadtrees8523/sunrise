---
name: update
description: "Update an existing Sunrise install in place, both halves: the integration on the Home Assistant box (through HACS or the built-in Marketplace, one restart) and the Claude-side plugins. Finds what's installed and what's new first, read-only; says in plain words what would change and asks once; keeps skills the owner edited unless they say yes for that skill; checkpoints, updates, checks that memory and the owner's own skills came through, verifies over MCP, then updates the plugins. Use when the owner says \"update sunrise\", \"is there a new version\", \"get the latest Sunrise\" or \"/update-sunrise\"."
---

# Sunrise update

Updates an install that already works: the integration on the box, then the
Claude-side plugins. Each half can be skipped. Every run doubles as a test of
the update experience, so record every snag.

**Getting onto the box is not this skill's job.** It belongs to
`connect-to-box:connect-to-box`, which this skill invokes first. A working box
record means one command, not the access ladder. **Installing is not this
skill's job either.** If Sunrise isn't on the box, say so and offer
`/sunrise:install`.

## Stance

Act as the implementation specialist, as in `/sunrise:install`: do every step
you can yourself and stop only for the owner's steps. Look before you change
anything. An update is a small, reversible change to a house that works; keep
it that way.

**Explain as you go.** When a term may be new to the owner (HACS, a commit, a
checkpoint, MCP), explain it in one plain sentence, and tell them they can say
**explain <term>** (`/sunrise:explain`) for more. After an explanation, pick
up at the same step.

## Hard rules

- **Read-only until the owner says yes** (Phase 2). One yes covers the plan;
  an owner-edited skill needs its own yes.
- Take a checkpoint before the first change, **on the box only**, and confirm
  it on disk (install's Phase 1 rules).
- **Never type, print or store passwords or tokens.** (connect-to-box →
  *Secrets*; use `box-secret`.) **Never guess usernames.** Ask.
- One change, then check it.
- **Never upgrade Home Assistant as a side effect.** If the new Sunrise needs a
  newer HA, stop and say so (install → *If the version is wrong, don't just
  upgrade it*).
- **Update in place; never reinstall over a working install.** Don't remove
  the config entry or delete `custom_components/sunrise/`, and change
  `<config>/sunrise/` only through Sunrise's own tools, never by hand. If the
  entry is lost, that's a failure to report, not a reason to start over.
- **Never replace a skill the owner edited without a yes for that skill.**
- **Memory and the owner's own skills must come through unchanged.** If they
  didn't, stop and tell the owner before anything else.
- **Run owner commands in the visible terminal panel** so you can read the
  result. Don't take "done" on trust.

## Where things go

- **Box facts** go in connect-to-box's record,
  `~/.claude/connect-to-box/boxes/<box-slug>/box.md`. Refresh its Sunrise line
  (commit, date) and *Baseline* block.
- **Update log** (one dated entry per run) goes in
  `~/.claude/connect-to-box/boxes/<box-slug>/sunrise-update-log.md`.

Secret *names* only, never values. Helpers, by full path: `box-secret` in
connect-to-box's `scripts/`, and `ha_ws.py` in `../install/scripts/` beside
this file (runs inside the HA container, token on stdin).

---

## Phase 1: find where things stand (read-only)

1. **Connect.** Invoke `connect-to-box:connect-to-box`. With a working record
   it's Step 0 and a refresh of *Take stock*. Run its Phase D only if `/mcp`
   doesn't show `sunrise` connected. Check `box-secret check ha-token`: with a
   token the update runs over the API; without one, its one click is an
   owner step, and nothing else changes.
2. **What the box runs.** Through the container, printing only these keys:
   ```
   docker exec <ha> cat /config/custom_components/sunrise/manifest.json
   docker exec -i <ha> python3 - <<'EOF'
   import json
   d = json.load(open('/config/.storage/hacs.repositories'))['data']
   for k, v in d.items():
       if v.get('full_name', '').lower() == 'quantumquadtrees8523/sunrise':
           print(k, {x: v.get(x) for x in ('full_name', 'installed', 'installed_commit',
                     'last_commit', 'version_installed', 'selected_tag')})
   EOF
   docker exec -i <ha> python3 - <<'EOF'
   import json
   for e in json.load(open('/config/.storage/core.entity_registry'))['data']['entities']:
       if e['unique_id'] == '<hacs id>':
           print(e['entity_id'], e['platform'], e.get('disabled_by'))
   EOF
   ```
   - **HACS tracks Sunrise by commit, not by version.** Sunrise has no tagged
     releases, so HACS installs the default branch and records the first 7
     characters of its commit (`installed_commit`; `version_installed` stays
     empty). The manifest `version` can stay the same across many updates, so
     the commit is what tells you where the box is.
   - HACS gives every downloaded repository an **update entity** (`unique_id`
     = the HACS id, usually `update.sunrise_update`). For Sunrise its
     `installed_version` and `latest_version` are those 7-character commits,
     and its release notes are empty, which is why you summarise from GitHub.
   - **Once Sunrise has tagged releases,** HACS tracks those instead:
     `version_installed` and the update entity's versions become tags such as
     `v0.2.0`, and the entity carries the release notes. Then compare tags,
     summarise from the release notes rather than commits (step 4: use
     `compare/<installed tag>...<latest tag>`), and *Rollback* can use HACS's
     Redownload with an earlier version. Handle whichever the box shows.
   - HACS only looks at GitHub on its own schedule, so `last_commit` may lag.
     GitHub is the truth for what's available.
   - On 2026.11+ HACS is the Marketplace. If `hacs.repositories` is missing,
     `ls /config/.storage` and read the same keys from the Marketplace's file.
   - No entry anywhere means Sunrise was copied in by hand. Note it; see
     Phase 4.
3. **The box's behavior repository.** Note HEAD and anything uncommitted:
   ```
   docker exec <ha> git -C /config/sunrise log --format='%h %an %s' -n 10
   docker exec <ha> git -C /config/sunrise status --porcelain
   ```
4. **What's upstream.** From this machine:
   ```
   curl -s https://api.github.com/repos/quantumquadtrees8523/sunrise/compare/<installed_commit>...main
   ```
   Read `status` (`ahead` or `identical`), `ahead_by`, each commit's message
   and the changed `files`. Turn it into **two to four plain bullets** about
   what the owner would notice: a new folder under `skills/` is a new thing
   to ask for (describe it from the README's table); a changed
   `custom_components/sunrise/bundled_skills/<name>/SKILL.md` is a built-in
   skill that changes; `custom_components/sunrise/*.py` is the tools;
   `claude-plugins/` is the Claude side; tests and docs alone are "nothing
   you'd notice". No hashes, no raw log. Note whether device behavior changed
   (`act`, `fix_device`, `routine`, the files behind them): that decides
   Phase 5's live check.
5. **HA version.** Read `homeassistant` from `hacs.json` at `main` (raw
   GitHub) and compare it with the HA version in the box record. Below it:
   **stop** (install → *If the version is wrong*). If the box crossed 2026.11
   since the install, HACS was migrated into the Marketplace: Sunrise should
   still be listed there (step 2), and owner steps use Marketplace wording.
   The update itself is the same either way.
6. **Skills the owner edited.** `list_skills` over MCP (or install Phase 4's
   JSON-RPC curl with `tools/call`). Note every built-in with `user_edited`
   or `update_available`. **Also check git:** a built-in whose `SKILL.md` has
   a `user` or `agent` commit after its newest `product` commit, or an
   uncommitted change, was edited. `list_skills` misses edits made by hand on
   the box (only `skill_update` marks a skill as edited), and the restart
   replaces those with the built-in; Phase 4 puts them back. A skill needs a
   decision only if this update changes its built-in text (step 4's files)
   or it already shows `update_available`. Skills the owner wrote themselves
   (`origin: user`) are never touched by an update.
7. **Snapshot for later:** `memory_list` (names, sizes, when changed), the
   list of skills, and the baseline as in install's Phase 0b steps 3 and 4
   (open repairs, log error categories, backup agents). Write the baseline to
   the box record.
8. **The Claude side.**
   ```
   claude plugin marketplace list --json   # the one whose source is quantumquadtrees8523/sunrise; normally "sunrise"
   claude plugin list --json               # installed versions and scope of sunrise@<mkt>, connect-to-box@<mkt>
   ```
   Upstream versions are in `claude-plugins/<plugin>/.claude-plugin/plugin.json`
   at `main` (raw GitHub). Claude Code only delivers a plugin update when that
   version changes.

**Nothing newer anywhere** (compare `identical`, plugin versions equal, no
`update_available`): say it in one line and stop. "Sunrise is up to date: the
box is on <date>'s version, and the plugins are sunrise <v> and
connect-to-box <v>."

---

## Phase 2: say what would change, ask once

In plain words, in one message:

- **What's new:** the bullets from Phase 1 step 4.
- **The restart:** Home Assistant restarts once. It's down for about <the
  box record's last `initialized in Ns`, plus ten seconds>; switches and
  lights keep working by hand, and automations pause until it's back. The
  whole update takes a few minutes.
- **What stays:** memory and the owner's own skills. You check them after.
- **Edited skills,** one line each: what they changed, and what the update
  changes. "Keep yours (the default), take the new one, or shall I show you
  the difference?" For one edited by hand, say plainly: "Sunrise didn't
  register this as yours, so the restart will swap in the built-in. Your text
  is in its history, and I'll put it back straight after unless you'd rather
  have the new one."
- **Going back:** a checkpoint on the box first; restoring it puts everything
  back as it is now (*Rollback*).
- **The Claude side:** sunrise <a> → <b>, connect-to-box <a> → <b>; it takes
  effect when Claude Code restarts.

Then: "Update both, just the box, just Claude Code, or not now?"

**Showing the difference:** what they changed (`behavior_log file=<name>
diff=true`) and what the update changes (the built-in `SKILL.md` at the
installed commit and at `main`, raw GitHub), each as a few plain sentences
and then the changed lines. The choices:

- **Keep mine:** nothing to do. Afterwards it shows `update_available`.
- **Take the new one:** Phase 4 step 1. Their version stays in the history.
- **Both:** after the update, write one text with their change and the new
  built-in, show it, and save it with `skill_update author=user`. It stays
  theirs. A refusal means the text drops a safety rule: fix the text.

Only the box: skip Phase 6. Only Claude Code: go to Phase 6.

---

## Phase 3: checkpoint

Exactly install's **Phase 1**: an HA backup with only `backup.local` (or the
local tarball), named `before-sunrise-update-<date>`, listed and confirmed on
disk with `ls -lt <config>/backups | head -3`. Record its name.

---

## Phase 4: update the box

1. **Skills the owner chose to replace.** Before the restart, put each back to
   its built-in text, so the restart updates it like any built-in:
   `behavior_log file=<name>`, take the newest commit by `product`, then
   `behavior_revert commit=<it> file=<name> author=user reason="owner chose the
   new built-in"`. Read back: `list_skills` shows it `user_edited: false`.
   Don't write the new text with `skill_update` instead: a skill saved that
   way stays marked as the owner's, and later updates would skip it.
2. **Get the update.** One of:
   - **Token route.** Copy `ha_ws.py` in as install Phase 3 step 1 does.
     1. Have HACS look now: `hacs/repository/refresh` with
        `{"repository":"<hacs id>"}`.
     2. Read `GET /api/states/<update entity>`. `latest_version` should match
        the first 7 characters of `main`. If it still lags, refresh once more.
     3. Install: `POST /api/services/update/install
        {"entity_id":"<update entity>"}`. No `version` (that means the newest
        commit) and no `backup` (HACS doesn't support it; Phase 3 is the
        backup). Fallback: `hacs/repository/download` with
        `{"repository":"<hacs id>"}`, the same call install uses.
     4. Confirm: `installed_version` equals `latest_version`, `in_progress`
        is false, the HACS file's `installed_commit` is the new one, and
        `custom_components/sunrise/manifest.json` is there.
   - **UI route:** owner step (below), then confirm as in 4.
   - **Copied in by hand** (no HACS entry): offer to add the repository to
     HACS and download it there (install Phase 3 steps 1 and 2). HACS writes
     over the old files in place and leaves the config entry and
     `<config>/sunrise/` alone, and later updates become one click.
3. **Restart once,** the way the box record says. Readiness is
   connect-to-box's *two checks that give false positives*: a fresh `Home
   Assistant initialized` line timestamped after the restart, nothing else.
4. **Check it came up.** The log has no `sunrise` errors (one benign
   `not been tested by Home Assistant` warning is expected). The config entry
   is still loaded: `GET /api/config/config_entries/entry` → the `sunrise`
   entry's `state` is `loaded`; without a token, Phase 5's tools answering
   shows it.
5. **Memory and the owner's skills came through.**
   ```
   docker exec <ha> git -C /config/sunrise log --format='%h %an %s' -n 10
   docker exec <ha> git -C /config/sunrise merge-base --is-ancestor <HEAD before> HEAD && echo HISTORY_KEPT
   docker exec <ha> git -C /config/sunrise diff --stat <HEAD before> HEAD -- memory/
   docker exec <ha> git -C /config/sunrise diff --name-only <HEAD before> HEAD -- skills/ | grep SKILL.md
   docker exec <ha> ls -R /config/sunrise/memory
   ```
   On the host, the same with `git -c safe.directory=<config>/sunrise -C
   <config>/sunrise`. Expect `HISTORY_KEPT`, your step 1 reverts, maybe a
   `user` `edited on disk` commit (hand edits Sunrise picked up), and one
   `product` commit `Sunrise <version>: built-in skills`. `memory/` changes
   only by that `edited on disk` commit. `SKILL.md` changes only for
   built-ins the owner didn't edit, plus the ones they chose to replace.
   `references/` (the rubric and house basics) refresh in every skill folder,
   the owner's own included; that's expected. Anything else: stop.
6. **Put back skills edited by hand** that the owner kept:
   `behavior_revert commit=<their newest edit commit> file=<name>
   author=user reason="keep the owner's hand edit"`. This also marks the
   skill as theirs, so later restarts keep it. Read back with `get_skill`.

**Exit:** HACS (or the Marketplace) shows the new commit installed, the entry
is loaded, the log is clean, and memory and the owner's skills are intact.

---

## Phase 5: verify over MCP

The restart dropped the MCP connection. If the `sunrise` tools fail, the
owner runs `/mcp` → `sunrise` → Reconnect; until then, use install Phase 4's
JSON-RPC curl. Tools the update added show up in this session only after a
reconnect.

Report pass or fail for each:

- [ ] the checkpoint exists on the box
- [ ] HACS/Marketplace shows the new commit installed
- [ ] the entry is loaded, with the log clean
- [ ] the tool list has Sunrise's tools (`house_map`, `act`, `routine`,
      `changes`, `list_skills`, `memory_list`, …), plus any the notes added
- [ ] `list_skills` has every skill in the repo's `skills/` at `main`,
      including the new ones (for example `welcome` and `explain`), and each
      new one is readable with `get_skill`
- [ ] edited skills are as the owner chose: kept ones `user_edited` (and
      `update_available` if the update changed them), replaced ones not
- [ ] `memory_list` matches the Phase 1 snapshot
- [ ] `house_map` answers (one harmless read)
- [ ] `behavior_log` shows the `product` commit from Phase 4 step 5
- [ ] only if the notes say device behavior changed: install Phase 5's `act`
      check on the test device from the box record (or memory), confirmed by
      a direct read of HA state and put back exactly
- [ ] **nothing else changed** against the Phase 1 baseline. A HACS
      `restart_required_<id>_main` repair can survive the restart; it's
      stale, so report it and say the owner can dismiss it.

Clean up `/tmp/ha_ws.py` on the host and in the container.

---

## Phase 6: update the Claude side

```
claude plugin marketplace update <mkt>
claude plugin update sunrise@<mkt>
claude plugin update connect-to-box@<mkt>
claude plugin list --json        # read the new versions back
```

Add `-s <scope>` if `claude plugin list` showed a scope other than user.
Inside Claude Code, the same is `/plugin` → Marketplaces → `<mkt>` → Update,
then each plugin under Installed → Update. Box records live outside the
plugins, so an update never touches them.

Tell the owner: **"Running sessions, this one included, keep the old skill
text until you restart Claude Code."** Optional, offer once: "/plugin →
Marketplaces → `<mkt>` → Enable auto-update, and new versions arrive by
themselves."

---

## Owner steps (say these exactly, one at a time, in the terminal panel where possible)

- **SSH access, token:** as in `/sunrise:install` (connect-to-box rung 4;
  `box-secret set ha-token`).
- **Update, UI route:** "Open Settings in Home Assistant. Near the top, under
  updates, pick **Sunrise update** and press Install. If it isn't there, open
  HACS (Marketplace on 2026.11 or newer) → Sunrise → ⋮ → Update information,
  then ⋮ → Redownload. Tell me when it's done."
- **Restart, if you can't:** "Settings → ⋮ (top right) → Restart Home
  Assistant → Restart."
- **MCP reconnect:** "In Claude Code run `/mcp`, pick `sunrise`, choose
  Reconnect."
- **Edited skills:** keep, take the new one, or both, one skill at a time.
- **Claude restart:** "Quit Claude Code fully and open it again to use the
  new skills."

## After a pass

Say it worked in one line. If `welcome` is new and `onboarding.md` is missing
or not finished: "Say **get started** and I'll walk you through setting up
your home." For other new skills, one line each on what to say. Don't start
any unasked.

## Rollback

- **Everything:** restore the Phase 3 checkpoint (Settings → System →
  Backups → `before-sunrise-update-<date>` → Restore; for the tarball, an
  owner step with HA stopped). It also puts memory back to that moment, so
  copy `<config>/sunrise/` aside first if anything was written since.
- **Just the integration:** HACS only lets you pick a version for a
  repository with releases, and Sunrise has none, so Redownload offers only
  the newest commit. Going back means the checkpoint, or copying
  `custom_components/sunrise/` from the previous commit
  (`https://github.com/quantumquadtrees8523/sunrise/archive/<commit>.tar.gz`)
  in through the container and restarting. `<config>/sunrise/` stays as it
  is; the old version puts its own built-ins back on start.
- **One skill choice:** `behavior_revert` the commit; both versions are in
  the history.
- **Plugins:** Claude Code has no downgrade. If the new plugin misbehaves,
  `claude plugin disable sunrise@<mkt>` and report it.

## Report

- the checklist
- versions before → after: the box's commit and date (and manifest version),
  HA and HACS/Marketplace, sunrise and connect-to-box plugin versions
- what changed, in plain words
- each edited skill: kept, replaced or combined
- the checkpoint name, and how to roll back
- each owner step taken, and how long it took
- **every snag, split into generalizable and box-specific**, as install does
- anything new worth trying ("say **get started**")

Add a dated entry to `sunrise-update-log.md` beside the box record with the
same content, and refresh `box.md`'s Sunrise line.
