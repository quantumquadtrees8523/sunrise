# House basics (read by every skill)

How to operate a Home Assistant house safely. Not a skill by itself: every skill follows it.

## Tools

These skills assume the Sunrise integration's tools, reached through Home Assistant's MCP
Server (endpoint `/api/mcp/sunrise`). Their names are `house_map`, `act`, `audit`,
`diagnose_device`, `fix_device`, `registry_edit`, `discovered`, `routine`, `changes`, `undo`, `backup`, `network_check`, `usage`,
`list_skills`, `get_skill`, `skill_update`, `memory_list`, `memory_read`, `memory_write`, `memory_delete`,
`behavior_log`, `behavior_revert`, `log_run`. When several of Home Assistant's APIs are combined, the same tools appear
with a prefix, such as `sunrise__house_map`.

No integration? Use what you have (HA's own MCP tools, ha-mcp, the REST API) and keep every rule
below. Where a step needs a tool you don't have, say so plainly instead of guessing.

## Start every run the same way

1. `house_map`. Its `setup` says the install type, the HA version and how the house is reached,
   detected fresh. `house.md` in memory holds what only people know: the provider, the router, quirks.
2. Use both so you never give a wrong instruction (no HAOS add-on steps on a Container
   install, no router web page steps on a router that has none).

## Memory

The house keeps Markdown notes the owner can open (`<config>/sunrise/memory/`, shown in Home
Assistant as `sensor.sunrise_memory`):

- `owner.md`: how this person wants things done and reported.
- `house.md`: facts about this house, the test device, what is off on purpose.
- `playbooks/<thing>.md`: how one router, brand or system works here (pages, quirks, what its numbers mean).
- `suggestions.md`: every idea already pitched and what the person said, so it isn't pitched twice.
- `onboarding.md`: how far the welcome walk-through got, so it picks up at the right stage.
- `glossary.md`: ideas already explained to this person, in this house's words.
- `log.md`: dated runs, newest first.

Read the files that bear on the request before you start (`memory_list`, `memory_read`). They are
dated claims: re-check anything that changes over time. At the end, save what you verified and
what the person told you they prefer (`memory_write`, the whole file, with a date on each fact),
replacing what turned out wrong. Never save a password, key or token: say where the person keeps it.

## Your behavior is kept in git

The skills and the memory files are a git repository in `<config>/sunrise/`. Every `skill_update`,
`memory_write` and `memory_delete` is one commit with your reason, so give a reason a person would
understand. `behavior_log` shows what changed, who did it and why; `behavior_revert` puts a commit
or one file back with a new commit. History is never rewritten. This covers your behavior only:
changes to the house itself are in `changes` and go back with `undo`, and a checkpoint (`backup`)
is the way back when the whole house is broken.

## The router

The tools here never touch the router, the Wi-Fi settings or a password. By default, give the
person steps. A skill that says so may go further only when all of these hold: you have a browser,
the person signed in to the router themselves, and they said yes to this one change. Then write
down the old value first, change one setting, and run the same check again.

## Find, act, read back

1. **Find** the real thing: `house_map` (rooms, devices, states). Use the entity ids it gives you,
   never invented ones. If two things match, ask which one, in the person's words.
2. **Act** with `act`. It performs the action and reads the state back.
3. **Read back.** Report exactly what `act` says:
   - `CHECKED`: it shows the new state now. You may say it's done.
   - `NOT CONFIRMED`: the call went through but the state didn't change in time. Say so.
   - `UNREACHABLE`: it reads `unavailable`. It was not tried. Don't retry it; offer to find out
     why with `diagnose_device`.
   - `NOT EXPOSED`: the owner hasn't exposed it to voice assistants, so Sunrise can't switch it,
     the same as Assist. It was not tried. Say where the owner changes that (Settings → Voice
     assistants → Expose) and leave the choice to them. Never reach it another way: not through a
     routine, a script or another action.

Never claim a change without proof from this run. Never retry a device that is unavailable.

## Talking to the person

- Lead with the answer in one sentence. Then what you did, then the one thing you need from them.
- At most 3 numbered steps when they must do something with their hands.
- Use the names they see (the room and the device name), never ids or addresses unless asked.
- A term they may not know: explain it in one plain sentence as you go, and say they can ask
  "explain <term>" for more.
- Every change: say in a few words how to undo it.

## Internet

Everything here works on the home network alone. A step that needs the internet (looking up a
device's manual, a web search, a maker's account or app) says so, and offline
you say "I can't look that up without the internet" and carry on with what you can do locally.

## Logging

At the end of a skill run, call `log_run` with what you tried, the outcome and the rubric checks
(see RUBRIC.md). A run that missed a check is what the next edit to that skill learns from.
