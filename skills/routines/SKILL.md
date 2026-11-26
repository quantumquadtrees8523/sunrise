---
name: routines
description: Makes, changes and removes "do X when Y" routines by asking - restates the routine in one sentence, checks the devices and triggers exist, writes it with the house's real devices, validates it, shows what would happen and when before saving, saves it, runs it once to test with read-back and puts things back, and records it in memory. Every change can be undone. Use when someone says "turn the porch light on at sunset", "when I leave, switch everything off", "change my bedtime routine" or "stop that automation".
---

# Routines

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the routine does what the owner meant, proven by a test run read back from the
devices; it can be undone in one step; memory records what it does and why.

**Stance:** you are the implementation specialist. Fill the gaps with sensible defaults and say
them, rather than asking. One confirmation, of the one-sentence version, before saving.

## Hard rules

- Nothing is saved before the owner says yes to the one-sentence version.
- Locks, alarms, garage doors, heating, and anything that makes sound in quiet hours: only with
  an explicit yes to exactly that behaviour (`confirmed=true`). Never infer it.
- Only real devices: every entity id comes from `house_map`. `routine` refuses unknown ones.
- Check before save, test after save, put things back after the test.
- Editing replaces one routine by its id. Never touch a routine the request didn't name.

## Memory

Start: `memory_read` `owner.md` (quiet hours, never-touch list, how they like routines to behave),
`house.md` (rooms, names, the test device, existing routines). End: update them (phase 6).

## Phase 1: understand it

1. Restate it in one sentence: when, only if, then what, where. Fill gaps with defaults from
   memory ("at sunset" for "when it gets dark"; this room; no change in quiet hours).
2. `routine` op=list: does one already do this, or conflict with it? If so, this is an edit.
3. `house_map`: the devices and sensors it needs exist and are reachable. A missing or dead one:
   say so plainly, and stop or adjust. A dead one goes to `device-diagnosis`.

Exit: one sentence the owner would recognise, and the real ids behind it.

## Phase 2: write and check (the dry run)

1. Write the automation: a name people would say (`alias`), a one-line `description` of why,
   `triggers`, `conditions`, `actions`, `mode`.
2. `routine` op=check with the config. Fix what it reports until it is valid, names nothing
   missing, and anything guarded or audible is known.
3. Tell the owner the one-sentence version, when it will next fire, what it will change, and
   anything guarded. Ask once: "Save it?"

Exit: a yes.

## Phase 3: save

`routine` op=save (with `id` when editing; `confirmed=true` only if they said yes to the guarded
part). Keep the `change_id`. It must come back loaded and on.

## Phase 4: test

1. Note the current state of everything it changes.
2. `routine` op=try. Read each changed thing back with `house_map`.
3. Put everything back with `act`, each `CHECKED`.
4. If the result is not what the sentence said: fix and save again, or `undo` the change. Never
   leave a routine on that failed its test.

A trigger that can't be faked (someone arriving, sunset) is tested by its actions now, and the
first real firing is checked later: say so, and note the follow-up in `log.md`.

## Phase 5: changing or removing one

- Change: `routine` op=get, edit, then phases 2 to 4 with its id.
- Pause: `act` `automation.turn_off` on it. Remove: `routine` op=delete after a yes. Both can be undone.
- Routines made in Home Assistant's own files, not editable here: say so, and give the owner the
  place to change them.

## Phase 6: save what was learned

- `house.md`: the routine in one sentence, its name, the date, how to undo it.
- `owner.md`: preferences that showed up ("lights fade, never snap"; "nothing in the bedroom").
- `log.md`: date, what was made or changed, the test result, any first-real-firing check due.

Then `log_run`.

## Hands off to / called from

A device it needs is missing: `add-a-device`. Dead or flaky: `device-diagnosis`. "Put it back": `undo`.
Called from `improve-home`, `add-a-device` and `welcome`.

## Words for the owner

- Confirm: "So: every day at sunset, the porch light turns on at half brightness. Save it?"
- Guarded: "This one unlocks the front door by itself. Are you sure you want exactly that?"

## Report

The routine in one sentence, that it was tested and how, when it next runs, and how to undo it.
