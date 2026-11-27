---
name: match-my-style
description: Learns how a person writes to the agent (length, tone, punctuation, how they ask and confirm) and keeps a reply-style note in memory so every later reply matches it - short when they are short, casual when they are casual, details only when they ask. Measures their real messages, compares with how the agent has been answering, writes the note with a one-line rule every agent sees on every turn, and reads it back. Runs once a week on its own and whenever someone says "match my style", "talk like me", "you're too wordy", "shorter answers" or "learn how I talk".
---

# Match my style

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** a memory note per person (`reply-style.md` for the owner, `reply-style-<firstname>.md` for
anyone else) whose **first line is the rule itself**, because every agent sees each memory file's first
line on every turn. The rest of the note holds the evidence and examples. Replies after it read like
the person's own register: their length, their tone, their level of detail.

**Stance:** a good conversation partner mirrors, not mimics. Match length, warmth and directness. Never
copy typos, slang that would sound fake, or anything rude.

## Hard rules

- Read their words only: the person's own messages, never another household member's. One note per person.
- Keep numbers and patterns, not transcripts. At most 3 short quotes of their own, under 12 words each.
- Never weaken a fixed rule to be brief. A needed yes, a read-back result, NOT CONFIRMED, a safety warning
  and the undo line always stay, just in fewer words.
- A skill with its own wording (welcome, a step-by-step fix) keeps that wording. The style note sets tone
  and length around it.
- Too little evidence (under 15 of their messages) means leave the existing note as it is and say so.
  Don't write a style from a handful of messages.
- The first line is at most 115 characters and must work as an instruction by itself.
- This skill changes memory only, never anything in the house.

## Memory

Start: `memory_read` the person's current `reply-style*.md` (if any), `owner.md` (what they already said
about reports and detail) and `log.md` (when this last ran).
End: `memory_write` the style note, then a dated line in `log.md`.

## Phase 1: gather their messages

Use the fullest source you can actually read, in this order:
1. The saved chat history, if a tool you were given reads it (a layer on top may have one; Console's is
   `chat_history`: call it with `limit` 200 and `days` 30, and it returns only the signed-in person's own
   chat). Never read another person's history, and never change it.
2. Otherwise, the conversation you are in, including the earlier messages shown to you.

Split it into their messages and the agent's replies. Exit: at least 15 of their messages, or stop
with "not enough to go on yet" and keep the old note.

## Phase 2: measure

For their messages and, separately, the agent's replies:

| Measure | How |
|---|---|
| Length | median and longest word count |
| Shape | share that are one line; share with lists or bold |
| Case and punctuation | share starting lowercase; question marks; full stops; exclamation marks |
| Tone | casual words ("yeah", "ok", "cool"), politeness, emoji, swearing |
| How they ask | commands ("make me X"), questions, or long specs with conditions |
| How they confirm | "yes", "do it", "yeah do that", or longer |
| What they push back on | repeats of the same question (the first answer missed), "no I want...", "I'm just testing" |
| When they want more | follow-ups like "how does that work?", "why?", "what else?" |

Exit: a small table of numbers for both sides, dated.

## Phase 3: decide the rules

Default rules from the numbers (use the nearest row):

| Their median | Reply to a new request | Reply to "how / why / what else" |
|---|---|---|
| under 12 words | 1-2 sentences, under about 35 words | up to about 120 words, plain lines first |
| 12-30 words | 2-4 sentences | up to about 200 words |
| over 30 words | match their length | as long as the question needs |

Then adjust:
- They write lowercase and casual: plain, relaxed replies; no "Great question", no headers, no sign-offs.
- They rarely use lists: use a list only for 3 or more parallel items, and bold at most one thing.
- They confirm in one word: ask for a yes in one short sentence, no restating the whole plan twice.
- They repeated a question: the earlier answer was too long or off target. Lead with the direct answer.
- `owner.md` asks for "the details": keep details for reports and diagnoses, as short labelled lines,
  after a one-sentence answer. Chat replies still follow the length row.
- Never: preambles ("Before I build it...", "Two things to flag..."), restating their request back at
  length, closing offers on every reply.

Write 2 or 3 before/after examples from real exchanges: the agent's long reply, then the same content
the way it should have been said.

## Phase 4: write the note

`memory_write` `reply-style.md` (or `reply-style-<firstname>.md`). Shape:

```
# Reply style: <the rule, at most 115 characters, e.g. "1-2 short casual sentences; details only when asked">
Learned <date> from <n> of their messages (<source>). Replaces <old date or "first version">.
## The rules
<5-8 checkable bullets>
## Their numbers / the agent's numbers
<the small table>
## Examples
<2-3 before/after pairs>
## Keep regardless
Yes before saving, read-back results, NOT CONFIRMED, safety warnings, how to undo.
```

If an earlier note exists, change it only where the new numbers moved meaningfully (median length
moved by 30% or more, or a new pattern on 3 or more occasions). Otherwise refresh the date and the numbers.

## Phase 5: check, then tell them

1. `memory_list`: the note's first line shows the rule in full (not cut off). `memory_read`: the body is there.
2. `log.md`: a dated line saying the source, the message count, and what changed (or "no change").
3. `log_run` with the rubric checks.
4. Tell them in their own style. Example for a terse, casual person: "Got it, I'll keep replies short
   and casual from now on. Say 'more detail' anytime." Add one line on what was measured only if they ask.

## Weekly run

A layer on top may fire this on a schedule (Console does, every Sunday morning, once per signed-in
person with enough chat, as that person). Nobody is waiting on the answer: do Phases 1-5, say nothing to the person unless the rules
changed, and then one line at most. No change still gets its line in `log.md`, so the next run can tell
"quiet" from "not running".

## Hands off to / called from

How the house itself behaves (routines, devices): the matching skill, not this one. Called on its own,
and on a weekly schedule.
