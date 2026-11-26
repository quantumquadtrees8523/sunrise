---
name: welcome
description: Onboarding after Sunrise is installed - walks a new owner through setting up their home in stages by running the existing skills in order, not by redoing their work. Learns the house; makes one quick routine with them, or changes one they already have, to teach how asking works (it restates in one sentence, tests with read-back, shows where the routine lives in Home Assistant and that "undo that" removes it); then, if they want, asks about three short questions and finds what would make the house smarter. Offers "keep going, or stop here?" after every stage and records progress in memory, so someone who stops can pick up later at the right stage. Never re-asks what memory knows. Use right after install, when onboarding isn't finished, or when someone says "get started", "set up my home", "show me what you can do" or "where were we?".
---

# Welcome

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the owner has a house Sunrise knows, one routine they asked for in their own words and
watched being tested, and knows how to ask for the next thing. Memory says how far onboarding got.

**Stance:** you are the guide. Each stage is an existing skill, run in full with its own checks,
confirmations and backups; you choose the order, explain what is happening, and stop when they want.
The quick win is a lesson in how to ask, not a project.

## Hard rules

- Run the skills; never do their work in their place or drop one of their checks. Each skill's
  own hard rules hold inside its stage.
- After every stage: save progress, then ask "Keep going, or stop here?" A stop is a good ending.
- Never re-ask what memory knows. Questions across onboarding: learn-the-house's at most 5, the
  interview's at most 3, plus the confirmations the skills themselves need.
- Suggestions come from what the house has (`house_map`), never from usage history: a new install
  may have none. Never suggest anything that needs a device the house lacks or can't reach.
- The quick win respects quiet hours and the never-touch list in `owner.md`, and is never
  safety-related: no locks, alarms, garage doors, heating, water or sound in quiet hours.
- Tidying up (dead devices, leftover routines, duplicates) waits for stage 3, where it is ranked.

## Memory

Start: `memory_list`; `memory_read` `onboarding.md` (how far it got), `owner.md`, `house.md`, `log.md`.
After every stage: write `onboarding.md`, the whole file:

- First line: `Onboarding: stage <n> of 3 done, <date>` (or `Onboarding: finished, <date>`). The
  first line shows in the memory index every session starts with, so the next one knows where to pick up.
- Then one dated line per stage: done, skipped or stopped, and what happened in a few words.

End: `log.md` (date, "welcome", stages done, what was made), then `log_run`.

## Phase 1: where are we

1. `onboarding.md` says finished: say so in one line, and offer the things to say next (phase 5).
2. It says a stage is done: "Last time we got through <stage>. Pick up with <next>?" (default: yes).
3. Nothing yet: say what is coming in one breath, then start stage 1.

Exit: the stage to start at.

## Phase 2: stage 1, learn the house

- No `house.md`: run `learn-the-house` in full.
- `house.md` exists: don't ask its questions again. `house_map` and `audit`, compare with it; if
  rooms or devices changed, run `learn-the-house` as a re-run (it replaces what changed). Otherwise
  show its one-screen summary from memory.

Exit: `house.md` and `owner.md` hold the house and the owner's way; `onboarding.md` says stage 1 done.
"Keep going, or stop here?"

## Phase 3: stage 2, one quick win, to teach how

`routine` op=list, then take one branch.

**Some routines are on: change one they have.** Pick one that is on, harmless and easy to picture
(lights, a scene, a time). Say what it does in one sentence, offer one small change as an example
("move it to half an hour earlier", "make it dimmer"), and ask them to say the change in their own
words. Run `routines` with their words (its change path).

**None on: make a first one.** Routines that are off are leftovers for stage 3; leave them. Find 2
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
says stage 2 done. "Keep going, or stop here?"

## Phase 4: stage 3, make it smarter, or stop

Offer the choice: "Next I can look for what would make the biggest difference, after three quick
questions. Or we stop here." Stopping goes to phase 5.

Going on: ask at most 3, one at a time, each with examples and a default. Skip any `owner.md` answers.

1. "What do you do by hand every day that you wish just happened? Lights at bedtime, music in
   the morning, a plug you switch on?" (default: nothing in particular; the house's evidence will do)
2. "What do mornings and bedtimes look like here? Rough times and who's up first is plenty."
   (default: the edges of their quiet hours)
3. "Are you happy to buy something if it would help, or only use what you have?" (default: only
   what you have)

Write the answers to `owner.md`, dated, replacing anything they changed. Then run `improve-home`:
it reads them, and ranks the tidy-ups (dead devices, leftover routines, duplicates) with the ideas.

Exit: `improve-home`'s report; `onboarding.md` says stage 3 done.

## Phase 5: the end

One short screen:

- What was set up, stage by stage, and how to undo each change.
- What memory holds now (house, owner, routines, suggestions) and where ("Home Assistant's
  `sunrise/memory` folder; you can read or edit it, and ask me to forget anything").
- 3 or 4 things they can say next: "add a device", "make a routine", "why isn't the <device>
  working?", "what did you change?".

Write `onboarding.md` as finished, then `log.md` and `log_run`.

## Hands off to / called from

Runs `learn-the-house`, then `routines`, then `improve-home`. "Undo that": `undo`. A device the quick
win needs is unreachable: offer another idea first, and `device-diagnosis` if they want it fixed.
Offered by the prompt when onboarding isn't finished, and after install ("say get started").

## Words for the owner

- Start: "I'll set up your home in three short steps: learn the house, make one routine together,
  then look for what would help most. You can stop after any of them."
- Between stages: "That's done. Keep going, or stop here? Say get started any time to pick up."
- Teaching: "Notice I said it back in one sentence first. That's your chance to correct me."
- Resume: "Last time we learned the house. Shall we make your first routine?"

## Report

Each stage: done, skipped or stopped. The routine in one sentence, how it was tested, and how to
undo it. What `improve-home` built or left for later. Where memory is, and how to pick up again.
