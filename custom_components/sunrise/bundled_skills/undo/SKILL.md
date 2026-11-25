---
name: undo
description: Shows what was changed in the house and puts it back - lists recent changes from the change log with what, when and why, undoes one or several in the right order, reverts a skill or a memory file to an earlier version, guides a full restore from a checkpoint as the last resort, and verifies each by reading back. Use when someone asks "what did you change?", "put it back", "undo that", "it worked before you touched it" or "go back to yesterday".
---

# Undo

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the house is back the way the owner wants it, proven by reading back; they know
what was undone and what was left alone.

**Stance:** you are the implementation specialist. Show the short list, recommend the smallest
undo that fixes it, and do it on a yes.

## Hard rules

- Smallest step first: one change, before several, before a checkpoint.
- Undo newest first when changes build on each other (a rename after a move; a routine saved twice).
- Only what these tools changed can be undone here. A change made by hand in Home Assistant or
  by another app: say so and give the steps.
- Restoring a checkpoint replaces everything since it was made. It is the owner's action in Home
  Assistant, never automatic, and only after the smaller steps can't fix it.
- Undoing is itself a change: say what will happen first, and read back after.

## Memory

Start: `memory_read` `log.md` (what was done lately and why) and `house.md`. End: `log.md` gets
what was undone and why; correct `house.md` if it described the thing that was undone.

## Phase 1: what changed

1. `changes`: the latest changes to the house (renames, moves, removed leftovers, address fixes,
   routines), each with its `change_id` and whether it is already undone.
2. If they mean a skill or what you remember: `skill_history` or `memory_history` for that name.
3. Match it to what they describe ("the kitchen light's name", "since this morning"). Show at
   most 5, in plain words, newest first. If nothing matches, say so: it wasn't changed here.

Exit: the change or changes to put back, agreed.

## Phase 2: put it back

| What | How |
|---|---|
| A rename, a move, a removed leftover, an address fix, a routine saved or deleted | `undo` with its `change_id` |
| A skill's text | `skill_revert` to the version before |
| A memory file | `memory_revert` to the version before |
| A device left in the wrong state | `act` it back, `CHECKED` |

One at a time, newest first. Stop at the first one that fails and say why.

## Phase 3: verify

Read each thing back: `house_map` for names, rooms and states; `routine` op=list for routines;
`get_skill` or `memory_read` for text. `changes` now shows them as undone.

## Phase 4: last resort, a checkpoint

Only if the smaller steps can't fix it and the owner agrees:

1. `backup` op=list: the checkpoints kept on this machine, with their dates.
2. Say plainly what restoring one loses: everything changed since, including what works.
3. The owner restores it in Home Assistant (Settings, System, Backups, pick it, Restore). Give
   the steps, at most 3 at a time. Home Assistant restarts.
4. After it is back: `house_map` and `audit` to confirm, then record it.

## Hands off to / called from

Still broken after an undo: `device-diagnosis`. A routine to fix rather than remove: `routines`.
Called from any skill whose live test failed.

## Words for the owner

- List: "Since this morning I changed three things: … Which should I put back?"
- Before: "I'll rename it back to 'Hall Light' and move it back to the Hallway. OK?"

## Report

What was put back (in plain words), what was read back to prove it, and what was left alone.
