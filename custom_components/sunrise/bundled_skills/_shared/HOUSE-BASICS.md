# House basics (read by every skill)

How to operate a Home Assistant house safely. Not a skill by itself: every skill follows it.

## Tools

These skills assume the Sunrise integration's tools, reached through Home Assistant's MCP
Server (endpoint `/api/mcp/sunrise`). Their names are `house_map`, `act`, `audit`,
`profile_get`, `profile_update`, `diagnose_device`, `fix_device`, `registry_edit`, `undo`, `backup`,
`network_check`, `usage`, `suggestions`, `list_skills`, `get_skill`, `skill_update`, `skill_history`,
`skill_revert`, `log_run`, `memory_list`, `memory_read`, `memory_write`, `memory_delete`, `memory_history`,
`memory_revert`. When several of Home Assistant's APIs are combined, the same tools appear
with a prefix, such as `sunrise__house_map`.

No integration? Use what you have (HA's own MCP tools, ha-mcp, the REST API) and keep every rule
below. Where a step needs a tool you don't have, say so plainly instead of guessing.

## Start every run the same way

1. `profile_get`. It says the install type, the HA version, what you can reach and the router. If
   it's missing or older than a week, learn it with `network_check` and `house_map` and save it with `profile_update`.
2. Use the profile so you never give a wrong instruction (no HAOS add-on steps on a Container
   install, no router web page steps on a router that has none).

## Memory

The house keeps Markdown notes the owner can open (`<config>/sunrise/memory/`, shown in Home
Assistant as `sensor.sunrise_memory`):

- `owner.md`: how this person wants things done and reported.
- `house.md`: facts about this house, the test device, what is off on purpose.
- `playbooks/<thing>.md`: how one router, brand or system works here (pages, quirks, what its numbers mean).
- `log.md`: dated runs, newest first.

Read the files that bear on the request before you start (`memory_list`, `memory_read`). They are
dated claims: re-check anything that changes over time. At the end, save what you verified and
what the person told you they prefer (`memory_write`, the whole file, with a date on each fact),
replacing what turned out wrong. Never save a password, key or token: say where the person keeps it.

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

Never claim a change without proof from this run. Never retry a device that is unavailable.

## Talking to the person

- Lead with the answer in one sentence. Then what you did, then the one thing you need from them.
- At most 3 numbered steps when they must do something with their hands.
- Use the names they see (the room and the device name), never ids or addresses unless asked.
- Every change: say in a few words how to undo it.

## Internet

Everything here works on the home network alone. A step that needs the internet (looking up a
device's manual, a web search, a cloud account like the WiZ or My Spectrum app) says so, and offline
you say "I can't look that up without the internet" and carry on with what you can do locally.

## Logging

At the end of a skill run, call `log_run` with what you tried, the outcome and the rubric checks
(see RUBRIC.md). A run that missed a check is what the next edit to that skill learns from.
