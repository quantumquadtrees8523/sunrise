---
name: improve-home
description: Makes the house more connected - links what the house already knows (who is home, the time and sun, the internet, a phone's battery, what is playing) to what it can do on another device (lights, speakers, notices to a phone, a dashboard), walking a catalogue of moments in the day, adding what people in the community have built with the same kinds of devices, and planning purchases to a budget when the owner wants the house to do more. Leads with one finished idea built from this house's real devices and asks one yes, builds it with a backup and a live test, offers the next link in the chain, and remembers what was accepted or declined. Use when someone asks "how can my home be smarter?", "what cool things can you do?", "what should I automate?", "what have other people built?", "what should I buy next?" or "I have $200, what would make the biggest difference?".
---

# Make the house more connected

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** one connection the owner said yes to is built, tested with read-back and undoable; the
next is offered; memory knows what was pitched, built, declined, and any budget they gave.

**The idea:** a house gets smarter when something it already *knows* makes something *happen*
somewhere else. "The phone got home, so the lights come on." "The internet dropped, so the phone
gets a notice." Pitch connections like these, never a tour of features or a tidy-up list.

**Stance:** you have set up a hundred homes. Do the looking yourself, then come back with one
finished idea in the owner's words and one question. You suggest; the owner decides.

## Hard rules

- Every idea uses this house's real devices and people by the names they use, and cites evidence
  (a habit from `usage`, a signal nothing reads, a routine they kept on). No evidence, no idea.
- Lead with **one** idea, fully worked out; at most two more, one line each; **one** yes/no question.
  Never end with "which would you like?" or a menu.
- Never pitch what `suggestions.md` holds, whatever the answer was, or what `owner.md` rules out.
- Tidy-ups and repairs are not ideas. Raise one only as a step inside the idea it blocks.
- Prefer a signal over a clock: sunset over "16:30", "the phone got home" over "18:00".
- Home Assistant reacts to changes, not standing states: say what will really happen, and offer
  the nearest honest version of "whenever the phone is home the light is at 100".
- Prefer what they own; buying is a plan to their budget, never a sales pitch (phase 6).
- Prefer what works on the home network without a cloud service; say when one needs the internet.
- Nothing safety-related (locks, alarms, garage doors, heat, water, anything that leaves the house
  unlocked or unattended) is automated without an explicit yes to that exact behaviour.
- Quiet hours: no sound and nothing changing by itself then unless they asked for it.
- Building anything: `backup` first, dry run, live test with read-back, and it must be undoable.

## Phase 1: what is known, and two lists

`memory_read` `owner.md`, `house.md`, `suggestions.md`, `log.md` and the `playbooks/` that bear on
it: the people and their devices, quiet hours, who gets which notices, named looks ("night mode"),
what they asked for and haven't got, a budget, every idea already pitched. Then from `house_map`,
`usage` (14 days, 30 if quiet) and the routines that are on, list:

- **Signals (what it can know):** people and phones (home/away, battery); time (sunrise, sunset,
  weekday, quiet hours); weather, calendar; the house itself (internet, last good backup, updates,
  unreachable count); activity (a TV, console or speaker starting, a light switched by hand, a
  power reading); sensors (motion, doors, temperature) if any.
- **Responses (what it can do):** light (brightness, warmth, colour, a named look); sound (play,
  move, group rooms, say something out loud); notices to a phone or tablet (check it is exposed);
  a dashboard for a room or a purpose.

Mark what is **already connected** (each routine that is on) and what **nothing reads**.

## Phase 2: walk the day

| Moment | Recipes (signal → response) |
|---|---|
| Waking up | alarm hour or sunrise → lights ramp warm to cool; → music or a spoken morning brief |
| Leaving | last person away → lights off, music stops; → a notice if something was left on |
| Coming home | a phone arrives → the right look for the hour; → the music they were playing resumes |
| Evening | sunset → warm light in the rooms in use; the house's named evening look |
| Play | the TV or console starts → the room dims, music pauses; stops → back as it was |
| Bedtime | bedtime hour or the last light off → the rest off, speakers stop |
| Keeping watch | internet down, a device dropped, no backup, battery low → a notice to the right person |
| One place | the routines, the music or one room → a dashboard with toggles |
| Talk to it | a spoken request → a spoken reply on a speaker in that room |

Mark each: **ready** (both ends exist, nothing connects them), **one step away** (one owner step
first: expose a phone, sign in to a music service, power-cycle a speaker; say which) or **needs a
purchase**.

## Phase 3: what others have built

When a web search tool is there (Console's `web__search`, or your own) and the internet is up,
always run 2-4 searches before pitching, for what people built with **this house's kinds of devices**, e.g. "Home Assistant
community automation ideas smart speakers phone presence lights". Prefer the Home Assistant
community forum, its blueprint exchange and owner forums over shops and listicles.

- Queries name only kinds of devices, well-known brands and integrations. Never a person, a room
  name, an address, an id or anything from memory.
- Keep an idea only if it maps onto this house's signals and responses, and mark it like a
  recipe. Drop cloud-only versions when a local one exists, and anything touching safety.
- In the pitch, say where it came from in a few words ("people on the Home Assistant forum do
  this") and keep the link for the report.
- No search tool or no internet: skip this phase and say so in one line.

## Phase 4: choose and pitch

Drop what `owner.md` rules out and every recipe whose signal and response match a line in
`suggestions.md`, even in other words or as part of a bigger idea; "pending" counts. Rank: ready, then one step away, then
needs a purchase; an idea that extends something they use (a named look, a routine they kept on,
a `usage` habit) first; a moment with no connection yet before one that has some; crossing devices
before staying on one. Pitch the top one like this:

> **First I'd build this: when your phone gets home after dark, the living room comes on in your
> evening look.** Your phone already tells the house when you're home, and you switched those lights
> on by hand most evenings in the last two weeks. I'd test it by running it once now and putting the
> lights back. "Undo that" removes it. After that: a notice on your phone if the internet goes down,
> and music that pauses when the TV comes on. Shall I build the first one?

Say: when, what happens, on which devices by name, why this house, how it is tested and undone, any
owner step first. Plain words, no ids. All the best ideas need buying: ask whether to plan a budget.

## Phase 5: build it

1. `backup`, and confirm it is listed.
2. "Do X when Y": run `routines`. Music: `music-assistant`. A dashboard: `custom-cards`. A
   repeatable job for the agent: `build-a-skill`.
3. Prove it live where safe: send the real notice, run the light change and put it back, play at low
   volume outside quiet hours. One that can't be triggered for real (a battery at 20%) is run once
   as a test, and you say a test run skips the trigger.
4. A failed step means fix or stop, never "leave it on anyway". A device that won't answer: `device-diagnosis`.

Your first words say what the read-back proved: "Done and checked" only after a CHECKED read-back;
otherwise "Saved, but I couldn't confirm it works", and why. A tool answering "ok" is not a
read-back, and a notice you couldn't read back was not sent. Then say what now works in one sentence and offer the next recipe in the chain as one question
("Now that the lights know you're home, want the music to start too?"). Declined: "Fine, I won't bring that up again."

## Phase 6: a budget and what to buy

When the owner asks what to buy, names a sum, or said yes to planning one:

1. **The budget:** use the one in `owner.md`, or ask once ("under $50, up to $200, or more?").
2. **What it unlocks:** for each capability the house lacks (motion in a room, a door sensor, a
   smart plug, a speaker, a button by the bed), list the recipes it would make ready here, by name.
3. **Rank by what it unlocks per dollar**, and stop at the budget. Something already owned that
   needs only a repair or a sign-in comes first, at $0.
4. **Each item:** the capability; where it goes; the recipes it unlocks; how it connects with what is
   here (the connection types the house already uses; say if it needs a hub, and count the hub);
   that it works without the cloud; a price range, dated, from at most 4 searches in all. Name one
   or two example products only now that they have asked to shop; the right kind matters more than the brand.
   Answer fit questions (which hub, will it plug into the box) from `house_map` setup and `house.md`, not the owner:
   no radio listed there means none; plan for that and add "skip this if you already have one".
5. **The plan:** a short table (item, unlocks, about how much), the total, and what *not* to buy
   (what the house already covers). If nothing is worth buying, say so. Never buy, never ask for
   payment details. One question: "Want me to save this plan and set each one up when it arrives?" (`add-a-device`).

## Phase 7: save what was learned

- `suggestions.md`: one line per idea pitched today: date, moment, idea, evidence, where it came from
  (this house or a link), and the answer (accepted, declined, later). Old lines stay.
- `owner.md`: preferences learned and the budget, dated ("notices go to the iPad"; "about $150").
- `house.md`: the connection built, with date, signal, response and how to undo it; the recipes still
  one step away or waiting on a purchase, and what they wait on.
- `log.md`: date, what was pitched, what was built, test results, the shopping plan if one was made.

Then `log_run`.

## Hands off to / called from

Build a routine: `routines`; music: `music-assistant`; a dashboard: `custom-cards`; a repeatable job:
`build-a-skill`. A device that won't answer: `device-diagnosis`. After a purchase: `add-a-device`.
A term they don't know: `explain`. Called from `learn-the-house` and `welcome`.

## Report

What was built and tested (in the owner's words), what was offered next, what waits on an owner step
or a purchase, the shopping plan and its total if one was made, sources for outside ideas, and how
to undo each change. No ids unless asked.
