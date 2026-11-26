---
name: learn-the-house
description: First run in a house, and again whenever asked - walks the house once through Home Assistant, asks the owner at most five short questions, and fills memory with the rooms and devices, what is off on purpose, what is flaky, how the owner wants things done and reported, and a safe test device. Ends with a one-screen summary of what it now knows and where it is kept. Runs as the first stage of welcome; on its own, use after a move or big change, or when someone says "get to know my house" or "what do you know about my home?".
---

# Learn the house

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** memory holds an accurate, dated picture of this house and its owner's way, and every
other skill can start from it instead of asking again.

**Stance:** you are the implementation specialist. Read everything Home Assistant already knows.
Ask only what it can't know, at most 5 questions, one at a time, each with a default the owner can accept.

## Hard rules

- Read only. This skill changes nothing in the house; it writes memory.
- First names only, and only if offered. No addresses, no passwords, no account details in memory.
- Every fact is dated. On a re-run, replace what changed rather than adding a second version.
- The test device is something harmless and visible. Never a lock, garage door, alarm or heating.

## Phase 1: read the house

1. `memory_list`: empty means a first run; otherwise read what is there and re-check it.
2. `house_map`: its `setup` (how Home Assistant is installed, its version, how the house is
   reached), then rooms, the devices in each, what each can do, how each connects.
3. `audit`: what is unreachable, has no room, is duplicated or unclear; noisy integrations.
4. `network_check`: the router if Home Assistant knows it; hubs and coordinators.
5. `routine` op=list: what already runs by itself.

Exit: a draft of `house.md` with nothing from the owner yet.

## Phase 2: ask (at most 5, one at a time, each with a default)

1. "These can't be reached right now: <names>. Are any off or unplugged on purpose?" (default: none)
2. "Which light or plug may I switch off and on to test things? Something harmless you can see."
   (default: suggest one reachable light in the room they use most)
3. "How should I report: one line, or the details?" (default: one line, details on request)
4. "Are there hours when nothing should make sound or change by itself?" (default: 22:00 to 07:00)
5. "Anything I should never touch or automate?" (default: locks, alarms, garage doors and heating
   always need your yes)

Skip any question memory already answers. Stop asking the moment they want to move on.

## Phase 3: write memory

- `house.md`: rooms and what is in each (names as people say them), hubs and the router if known,
  how things connect, off on purpose, known flaky, the test device, existing routines.
- `owner.md`: how they want reports, quiet hours, never-touch list, who lives here (if offered).
- `log.md`: the date, "learned the house", counts, open questions.

Then `log_run`.

## Phase 4: show what you know

One screen: rooms and device counts, what can't be reached and why if known, the test device,
their preferences, and where it is kept ("in Home Assistant's `sunrise/memory` folder; you can
read or edit it, and ask me to forget anything").

## Hands off to / called from

Called from `welcome`, as its first stage; also run on its own when asked. Unreachable devices they did not turn off: `device-diagnosis`.
Things to tidy or improve: `improve-home`.

## Report

The one-screen summary. No ids or addresses unless asked.
