---
name: undo
description: Shows what was changed in the house and puts it back - lists recent changes from the change log with what, when and why, undoes one or several in the right order, puts a skill or a memory file back from the behavior history, guides a full restore from a checkpoint as the last resort, and verifies each by reading back. Use when someone asks "what did you change?", "put it back", "undo that", "it worked before you touched it" or "go back to yesterday".
---

# Undo

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** things are back the way the owner wants, proven by reading back; they know what was
put back and what was left alone. Show a short list, recommend the smallest undo, do it on a yes.

## Hard rules

- Smallest step first: one change, before several, before a checkpoint. Newest first when changes
  build on each other.
- Only what these tools changed can be undone here. For a change made by hand or by another app,
  say so and give the steps.
- Undoing is a change: say what will happen first, read back after, and note it in `log.md`.

## 1. What you do and remember (skills, memory)

1. `behavior_log` (add `file` for one skill or memory file; `commit` shows one with its diff).
   Show at most 5 in plain words, newest first: who, when, why.
2. `behavior_revert commit=<id>` reverses that one change. To put a single file back the way it
   was at some point, add `file=<name>`. Both make a new commit; nothing is lost.
3. Read back with `get_skill` or `memory_read`.

## 2. What changed in the house (names, rooms, addresses, routines)

1. `changes`: each has a `change_id` and says whether it is already undone.
2. `undo` with its `change_id`, one at a time. A device left in the wrong state: `act` it back.
3. Read back: `house_map` for names, rooms and states; `routine` op=list for routines.

Stop at the first one that fails and say why.

## 3. Last resort: a checkpoint

Only when the smaller steps can't fix it and the owner agrees.

1. `backup` op=list: the checkpoints kept on this machine, with their dates.
2. Say plainly what restoring loses: everything changed since, including what works.
3. The owner restores it in Home Assistant (Settings, System, Backups, pick it, Restore), at most
   3 steps at a time. Home Assistant restarts. Then `house_map` and `audit` to confirm.

## Hands off to / called from

Still broken after an undo: `device-diagnosis`. A routine to fix rather than remove: `routines`.
Called from any skill whose live test failed.

## Report

What was put back (in plain words), what was read back to prove it, and what was left alone.
