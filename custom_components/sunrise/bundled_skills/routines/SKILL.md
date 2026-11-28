---
name: routines
description: Makes, changes and removes "do X when Y" routines by asking, and suggests routines from how the house is used - restates the routine in one sentence, checks the devices and triggers exist, writes it with the house's real devices, validates it, shows what would happen and when before saving, saves it, runs it once to test with read-back and puts things back, and records it in memory. Every change can be undone. Use when someone says "turn the porch light on at sunset", "when I leave, switch everything off", "change my bedtime routine" or "stop that automation".
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

## Suggesting routines (nobody asked)

A short-term exception to the hard rules above, for routines only. When an agent is asked to suggest
routines (Console's nightly run, or "what routines would help?"), it may save **suggestions** without a
yes, because a suggestion is switched off and can't fire on its own. The household runs it by tapping it;
the agent that tracks the taps keeps it (`routine` op=keep) once it has earned that.

1. `memory_read` `owner.md` and `house.md`; `routine` op=list (don't suggest what a routine already does,
   or anything memory says the owner turned down); `usage` (14 days) for what is switched by hand at
   about the same time, or together, on most days. Its `follows` list is what the house heard: a door,
   window, motion or presence sensor changed (or a person came or went) and someone switched a thing by
   hand within two minutes, on at least 4 days and 6 times in 10. Each entry has its `evidence` and the
   `routine` that would do it, already checked against the routines the house has and the suggestions
   the household turned down.
2. Pick at most the number of suggestions asked for. Each needs evidence from `usage`: a time or a pairing
   that held on most days. No evidence, no suggestion. Prefer turning things off over turning them on.
   An entry in `follows` is evidence as it stands: save its `routine` unchanged, strongest first.
3. Write each like phase 2 (a name people would say, a one-line `description` with the evidence, e.g.
   "The den lamp went off by hand around 23:10 on 9 of the last 14 nights"). Then `routine` op=suggest.
   It refuses anything guarded, audible or not exposed, and anything Home Assistant doesn't have; drop
   those rather than working around them.
4. Never `act`, `try` or `keep` while suggesting: nothing in the house changes tonight.
   **Live suggestions**: only when the request says the owner wants suggestions live, save with
   `routine` op=suggest `on=true`. It then runs on its own trigger from now on, still labelled
   Suggested, and the owner keeps it (op=keep) or takes it back (op=dismiss, or `undo`). The same
   refusals apply. Never pass `on=true` on your own judgment.
5. `log.md`: the date and the suggestions made, by name.

**Listening (asked on a schedule, "what did the house hear?")**: this is the short form of the steps
above. Call `usage` once and look only at `follows`. Nothing there: change nothing and say so in one
line. Otherwise save each entry's `routine` with `routine` op=suggest, strongest first, up to the number
asked for (with `on=true` only if the request says the owner wants suggestions live), and reply with
one line: how many, by name. Don't read memory or other skills for this, and don't look for habits by
the clock: that's the full run above.

A suggestion that's no longer wanted goes with op=dismiss; the house remembers it, and `follows` never
offers that pair again. A kept one is an ordinary routine (phase 5).

## When the person's hand wins (nobody asks)

A routine is the house's guess; what someone just did by hand is what they want now. Sunrise enforces
this in code, with no model and nobody asked: when a routine's run switches a light, switch, fan or cover
away from what a person set it to in the last two hours, it stops that run and puts the thing back
(HA's logbook says so). When the same routine keeps doing it to the same thing at about the same time
(3 days in 14), Sunrise changes the routine to leave that thing alone at those hours: only that step,
wrapped in an "only outside these hours" check, labelled **Adapted**, its reason added to the
description, one entry in `changes` (op `routine_adapt`) and a line in `log.md`.

- `usage` reports both: `overruled` (each time the hand won) and `adapted` (each routine changed).
  Read them before changing a routine, and when someone asks "why didn't the lights come on?".
- Don't undo an adaptation or fight it with a new routine unless the person asks; it's what they did.
  "Put it back" is `undo` with its change_id.
- An adaptation is the house's best guess too. When editing an Adapted routine for another reason, keep
  its "Sunrise: leave the … alone" step unless the person says otherwise.

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
Called from `improve-home`, `add-a-device` and `welcome`, and by Console's nightly suggestions.

## Words for the owner

- Confirm: "So: every day at sunset, the porch light turns on at half brightness. Save it?"
- Guarded: "This one unlocks the front door by itself. Are you sure you want exactly that?"

## Report

The routine in one sentence, that it was tested and how, when it next runs, and how to undo it.
