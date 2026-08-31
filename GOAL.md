# Goal

The best current model should score around **80%**, not 98%.

A suite the top model maxes out can't measure the next model. Today Fable
scores 97.7% on the concepts quiz — so the quiz ranks weaker models fine but
tells us nothing about frontier progress. The goal is headroom without
tricks.

## How we keep headroom

- **Current questions.** What deploying a contract costs today, current
  protocol state, current tooling. Real builder knowledge that models trained
  a year ago get wrong. Graded against chain truth at grade time where
  possible, refreshed on a cadence otherwise.
- **Applied grading.** Transactions and code are graded by whether they
  work — the EVM decides, not a string match on prose.
- **Composition.** Multi-step build tasks. A model that's 95% per step lands
  ~60% on a ten-step task. No step is obscure; the length is the difficulty.

## Targets

| Section | Top model today | Why |
|---|---|---|
| Concepts | ~80% | current + practical questions restore headroom |
| Transactions | 50–75% | artifact must be correct, not close |
| Building | 50–75% | code must pass hidden tests on a real chain |

- A model + ethskills (or any skill pack) should jump well above the bare
  score. That gap is a feature — it proves the suite measures real,
  learnable knowledge, and it measures the skill pack too.
- When a section's top score creeps past ~90%, add current material until it
  comes back down. Saturation is a maintenance signal, not a milestone.

## Rules that keep scores honest

- Every result is bound to a manifest hash of the full task corpus and
  grader source. Change a task, and old runs go to legacy — never compared
  against new runs.
- No public RPCs, no committed keys, and **no model runs without Austin's
  explicit ok** — runs cost money and land in results.
