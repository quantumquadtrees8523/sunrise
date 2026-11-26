---
name: welcome
description: Onboarding after Sunrise is installed - walks a new owner through setting up their home in stages by running the existing skills in order, not by redoing their work. Learns the house; brings in what's waiting (devices Home Assistant found but nobody added, or added with no room or a name nobody says) with one list to correct, then adds and tests each; makes one quick routine with them, or changes one they already have, to teach how asking works (it restates in one sentence, tests with read-back, shows where the routine lives in Home Assistant and that "undo that" removes it); then, if they want, asks about three short questions and finds what would make the house smarter. Offers "keep going, or stop here?" after every stage and records progress in memory, so someone who stops can pick up later at the right stage. Never re-asks what memory knows. Use right after install, when onboarding isn't finished, or when someone says "get started", "set up my home", "show me what you can do" or "where were we?".
---

# Welcome

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the owner has a house Sunrise knows, its waiting devices added and placed, one routine
they asked for in their own words and watched being tested, and knows how to ask for the next
thing. Memory says how far onboarding got.

**Stance:** you are the guide. Each stage is an existing skill, run in full with its own checks,
confirmations and backups; you choose the order, explain what is happening, and stop when they want.
The quick win is a lesson in how to ask, not a project.

## Hard rules

- Run the skills with all their checks and hard rules; never do their work in their place.
- After every stage: save progress, then ask "Keep going, or stop here?" A stop is a good ending.
- Never re-ask what memory knows. Questions across onboarding: learn-the-house's at most 5, one
  for the whole waiting list, the interview's at most 3, plus the confirmations the skills need.
- Suggestions come from what the house has (`house_map`), never from usage history: a new install
  may have none. Never suggest anything that needs a device the house lacks or can't reach.
- The quick win respects quiet hours and the never-touch list in `owner.md`, and is never
  safety-related: no locks, alarms, garage doors, heating, water or sound in quiet hours. Nothing
  safety-related is added from the waiting list without the owner's yes to that device by name.
- Tidying up (dead devices, leftover routines, duplicates) waits for stage 4, where it is ranked.

## Memory

Start: `memory_list`; `memory_read` `onboarding.md` (how far it got), `owner.md`, `house.md`, `log.md`.
After every stage: write `onboarding.md`, the whole file:
- First line: `Onboarding: stage <n> of 4 done, <date>` (or `Onboarding: finished, <date>`). The
  first line shows in the memory index every session starts with, so the next one knows where to pick up.
- Then one dated line per stage: done, skipped or stopped, and what happened in a few words.

End: `log.md` (date, "welcome", stages done, what was made), then `log_run`.

## Phase 1: where are we

1. `onboarding.md` says finished: say so in one line, and offer the things to say next (phase 6).
2. It says a stage is done: "Last time we got through <stage>. Pick up with <next>?" (default: yes).
   An older `of 3` file: its stages 2 and 3 are stages 3 and 4 here; offer stage 2 once.
3. Nothing yet: say what is coming in one breath (the start words), then start stage 1.

## Phase 2: stage 1, learn the house

- No `house.md`: run `learn-the-house` in full.
- `house.md` exists: don't ask its questions again. `house_map` and `audit`, compare; if rooms or
  devices changed, re-run `learn-the-house` (it replaces what changed), else show its summary.

Exit: `house.md` and `owner.md` hold the house and the owner's way; `onboarding.md` says stage 1 done.
"Keep going, or stop here?"

## Phase 3: stage 2, bring in what's waiting

Gather, asking nothing yet: **found, not added** (`discovered` op=list, with what each needs) and
**added, not set up** (`audit`: no room, or a name people wouldn't say), minus what `house.md`
says is off on purpose. None: "Nothing's waiting to be added.", save stage 2 done, go to stage 3.

Otherwise show ONE list: for each, a proposed name (the house's habit in `house.md`) and room (one
it has, or marked new), what needs the owner's hands ("needs your sign-in to <maker>"), and each
safety-related one named plainly ("Side Door lock"). One question: "Shall I set these up like
this? Change any name or room, or say skip, in one reply." (default: yes, as listed). A
safety-related one goes ahead only on a yes to it by name.

Then one at a time, in list order. **Found:** `add-a-device` from its phase 2 with the agreed name
and room; it accepts a plain-yes one with `discovered` op=accept and gives exact steps only where
the owner must sign in, enter a code or press a button on the device. **Not set up:**
`registry_edit` op=rename and op=set_area (op=create_area first for a new room), then test with
read-back by add-a-device's phase 4 rules. Stuck: say so, carry on; `device-diagnosis` at the end.

Exit: each one added, named, placed and tested, or left for later and why; `house.md` updated;
`onboarding.md` says stage 2 done. "Keep going, or stop here?"

## Phase 4: stage 3, one quick win, to teach how

`routine` op=list, then take one branch.

**Some routines are on: change one they have.** Pick one that is on, harmless and easy to picture
(lights, a scene, a time). Say what it does in one sentence, offer one small change as an example
("move it to half an hour earlier", "make it dimmer"), and ask them to say the change in their own
words. Run `routines` with their words (its change path).

**None on: make a first one.** Routines that are off are leftovers for stage 4; leave them. Find 2
or 3 ideas in `house_map`, each from devices that are there and reachable, and drop any `owner.md`
rules out:

| The house has | A first routine |
|---|---|
| phones or people Home Assistant sees come and go | "when the last person leaves, the lights go off" |
| lights that change warmth, never changed | warm light in the evening, cooler in the morning |
| speakers and a calendar | a spoken heads-up before an event, outside quiet hours |
| a motion sensor no routine reads | a light comes on with motion, and off a few minutes after |
| lights and nothing on a schedule | the porch or hall light on at sunset, off at bedtime |

Offer them in one sentence each, then: "Say the one you want in your own words. That's how you'll
ask for anything." Run `routines` with what they said, not with your wording.

**Either way, narrate the pattern as it happens.** Point out each of these once, in a few words:
1. It restated what you asked in one sentence before saving: if that sentence is wrong, say so.
2. It tested it and read the devices back: it only says done when the house shows it.
3. Where it lives: Home Assistant, Settings, Automations & scenes, under the name it was given.
4. "Undo that" puts it back, now or any day later. Run `undo` only if they say it.

Exit: one routine made or changed, tested, and the owner has heard the four points; `onboarding.md`
says stage 3 done. "Keep going, or stop here?"

## Phase 5: stage 4, make it smarter, or stop

Offer the choice: "Next I can look for what would make the biggest difference, after three quick
questions. Or we stop here." Stopping goes to phase 6.

Going on: ask at most 3, one at a time, each with examples and a default. Skip any `owner.md` answers.
1. "What do you do by hand every day that you wish just happened? Lights at bedtime, music in
   the morning, a plug you switch on?" (default: nothing in particular; the house's evidence will do)
2. "What do mornings and bedtimes look like here? Rough times and who's up first is plenty."
   (default: the edges of their quiet hours)
3. "Are you happy to buy something if it would help, or only use what you have?" (default: only
   what you have)

Write the answers to `owner.md`, dated, replacing anything they changed. Then run `improve-home`:
it reads them, and ranks the tidy-ups (dead devices, leftover routines, duplicates) with the ideas.

Exit: `improve-home`'s report; `onboarding.md` says stage 4 done.

## Phase 6: the end

One short screen:
- What was set up, stage by stage, and how to undo each change.
- What memory holds now (house, owner, routines, suggestions) and where ("Home Assistant's
  `sunrise/memory` folder; you can read or edit it, and ask me to forget anything").
- 4 or 5 things they can say next: "add a device", "make a routine", "why isn't the <device>
  working?", "what did you change?", "explain <anything>".

Write `onboarding.md` as finished, then `log.md` and `log_run`.

## Hands off to / called from

Runs `learn-the-house`, `add-a-device` per waiting device, `routines`, then `improve-home`. "Undo
that": `undo`. "Explain X": explain, then back to the same stage. A device the quick win needs is
unreachable: offer another idea, and `device-diagnosis` if wanted. Offered by the prompt when
onboarding isn't finished; started by the installer on a yes to "Set up your home now?".

## Words for the owner

- Start: "I'll set up your home in four short steps: learn the house, bring in any devices waiting
  to be added, make one routine together, then look for what would help most. You can stop after
  any of them, and if I say something technical, ask me to explain it."
- Between stages: "That's done. Keep going, or stop here? Say get started any time to pick up."
- Teaching: "Notice I said it back in one sentence first. That's your chance to correct me."
- Resume: "Last time we learned the house. Shall we bring in the devices that are waiting?"

## Report

Each stage: done, skipped or stopped. Each device brought in: name, room, test, or what it still
needs. The routine in one sentence, how it was tested, and how to undo it. What `improve-home`
built or left for later. Where memory is, and how to pick up again.
