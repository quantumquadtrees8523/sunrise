---
name: build-a-skill
description: Builds a new skill for this house, from a request or from work just finished in this conversation, so the same kind of result comes out the same way every time - recover what happened, capture how the owner likes it done as checkable rules, keep the general method in the skill and this house's facts in memory, then gap check, read-only dry run, backup, live test with read-back and put-back, safety gate, save. Use when someone wants a new skill, says "make this repeatable" or "remember how we did this", or wants to teach the agent how to do something in their house.
---

# Build a skill

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

A skill is a short instruction file (`SKILL.md`) the agent follows. It lives in the person's own
skills folder (`<config>/sunrise/skills/<name>/`), is checkpointed on every change and can be
reverted. A good one gives the same shape of result every run, done the way this owner likes it.

**Stance:** you are the implementation specialist. Make the calls and bring a finished draft.
Ask only what the source can't answer, at most 4 questions, one at a time.

## 1. Recover the source

- **From work just done:** re-read the whole conversation, not your summary of it. `log_run
  op=calls` lists the tool calls this session made. Write down: the goal and what "done" looked
  like when the owner accepted it; each step and what it found; dead ends; every correction,
  approval and "don't do that" from the owner; your own mistakes with the corrected fact.
- **From a request:** ask what should happen, when, in which rooms, and what "done right" looks like.

Exit: you can say the goal and the accepted result in two sentences.

## 2. Pick the kind of work (it sets the skeleton)

| Kind | Skeleton |
|---|---|
| Fix (something broke) | ground truth, measure, find what separates the failures, read the system in charge, hypotheses with evidence, one change at a time, same check again, soak |
| Feature (make something new) | goal and acceptance check, what already exists, decide with defaults, build in small checked steps, test the way the owner will use it |
| Routine (a recurring task) | preconditions, checklist with a check per step, standard result, put things back, report |
| Setup (install or move) | inventory and backup, plan with a way back, stages, check each stage, switch over |

Don't add steps the source didn't justify.

## 3. Capture the owner's way

Turn each owner signal into a rule someone could check after a run. Not "be brief" but "the report
is the state, the cause with its evidence, one recommended action, then what's unproven". Cover:
how decisions are made (one recommendation or a menu), what needs a yes first, how done is proven,
how results are reported.

## 4. Sort general from specific

For every remaining item ask: would this still be right in another house, with other brands?

- **Yes** → the skill: method steps, decision rules (evidence X means Y), and guards. A guard is a
  mistake named as a class: "acted on an old scan" becomes "date every observation and measure
  again before acting on anything that changes over time".
- **No** → memory, never the skill: names, rooms, models, addresses, page paths, quirks, baselines
  (`house.md`, `playbooks/<thing>.md`); this owner's personal preferences (`owner.md`).

The skill tells its reader which memory files to read at the start and which to update at the end.

## 5. Draft

Frontmatter `name` (lowercase-with-hyphens) and `description` (what and when). Then, in order:
what result it produces; the owner's way; hard rules; memory to read and write; phases, each with
a goal, how, and an exit condition; decision rules with a default for each; how done is checked;
exact wording for steps only a person can do; the report's shape. Point to the rubric with a
"Done means" line. Defaults instead of questions. Under 120 lines.

## 6. Gap check

`house_map` and `list_skills`. Does a skill already do this? Are the things it needs there and
reachable (not unavailable)? Say any gap plainly and stop or adjust.

## 7. Dry run, read-only

Walk the steps calling only read tools. List what it would change. No `act` yet. The owner
approves the draft before the live test.

## 8. Live test

1. Choose the test device: the one named in `house.md`; otherwise ask once for something harmless
   they can see, and save the answer to `house.md`. Never a lock, garage door, alarm or heating.
   If nothing can be switched, test read-only and say the live test was skipped.
2. `backup` (op=create) and confirm it is listed.
3. Run the steps for real with `act`; every step must come back `CHECKED`.
4. Put things back the way they were (the states you read before) and check those too.

A failed live step means fix the draft or stop, never "save anyway".

## 9. Safety gate (all must hold, or don't save)

- Nothing beyond the fixed rules: no lock, alarm or garage action without a yes in the moment;
  the router only as the rubric's S1 allows; no password typed or stored.
- Every change undoable, and read back after it is made.
- It doesn't weaken any fixed rule.

## 10. Self-test, then save

Check the draft against three cases: this house with memory empty (does the method still reach
the result and avoid the known mistakes?), a different house (does any step assume this one?), and
two similar requests (same checks and same report both times?). Fix what fails.

Then `skill_update` with the text and `reason: "new skill: ..."`, and read it back with
`get_skill`. Save this house's facts with `memory_write`. Tell the owner in a few lines: what the
skill does, what went to memory, which mistakes became guards, and what is still unproven.

## Share (optional)

Offer to write a copy with names and addresses replaced by placeholders for the person to share
by hand. Never upload anything. Memory stays home.
