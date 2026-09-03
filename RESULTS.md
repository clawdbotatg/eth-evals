# Results log

Raw result files are gitignored (`results-live/`, `exec-results/`,
`arena-runs/`). This file is the committed record of what was measured,
when, and what looked off. Newest first.

## 2026-09-03 — arena live-4b: same four models, 3 processes max (concurrency check)

Rerun of live-4 with `--max-procs 3` (a global gate; exactly three
`claude` processes at any time, verified with ps). Same 50 tasks. 18 min
wall. Watched at http://127.0.0.1:8790/#run=live-4b.

| model | 09-02 (3 procs) | live-4 (12 procs) | live-4b (3 procs) |
|---|---|---|---|
| fable | 38/50 | 32/50 | 35/50 |
| opus | 35/50 | 34/50 | 35/50 |
| sonnet | 21/50 | 20/50 | 23/50 |
| haiku | 16/50 | 14/50 | 12/50 |

Task-level flips between runs (up/down): fable +4/−1 vs live-4, opus
+2/−1, sonnet +5/−2, haiku +0/−2. Every model flips 2 to 7 tasks between
any two runs of this track.

**Fable, the 6 tasks it lost in live-4:**

| task | category | 09-02 | live-4 | live-4b | change |
|---|---|---|---|---|---|
| addr-erc8004-reputation | canonical-address | pass | FAIL | FAIL | still failing |
| addr-morpho-blue | canonical-address | pass | FAIL | pass | recovered |
| addr-universal-router | canonical-address | pass | FAIL | pass | recovered |
| live-usdc-supply | live-research | pass | FAIL | pass | recovered |
| tx-calldata-dai-transferfrom | live-tx | pass | FAIL | FAIL | still failing |
| tx-calldata-permit-2612 | live-tx | pass | FAIL | pass | recovered |
| proto-blob-cost-usd | protocol-current | pass | pass | FAIL | new loss |

Four of the six came back at low concurrency, two stayed down, and one
new task dropped. Only one "no address" reply in live-4 (`morpho-blue`),
none in live-4b.

**Verdict: noise, not a concurrency effect.** Fable's three runs land at
38, 32, 35 — a ±3 spread, the same band every other model shows (Sonnet
21/20/23, Haiku 16/14/12, Opus 35/34/35). Haiku got *worse* at low
concurrency, and Opus didn't move, so load does not explain live-4. A
load effect of one or two tasks can't be excluded on n=1 per condition,
but it is smaller than the run-to-run noise either way.

What this means for the track: **one 50-task run has about ±3 tasks
(±6 points) of noise.** Fable and Opus are tied within it (35/35 here).
Ranking two models on this track needs either 3+ runs each or a bigger
task set. Sonnet and Haiku are separated from the top pair by far more
than the noise, so the tier ordering holds.

## 2026-09-03 — arena live-4: four models, live track, closed-book, watched live

First real run through `arena.py` (`--tracks live --live-mode closed`,
concurrency 3 per agent, 12 claude processes at once, 7 min wall). Same
50 tasks as the 2026-09-02 rerun. Watched at http://127.0.0.1:8790/#run=live-4.

| model | passed | mean s/task | 2026-09-02 | flips |
|---|---|---|---|---|
| opus | 34/50 (68%) | 10.0 | 35/50 | 1 |
| fable | 32/50 (64%) | 7.3 | 38/50 | 6 |
| sonnet | 20/50 (40%) | 18.2 | 21/50 | 7 |
| haiku | 14/50 (28%) | 23.0 | 16/50 | 2 |

Per category (pass/total):

| category | opus | fable | sonnet | haiku |
|---|---|---|---|---|
| canonical-address | 22/24 | 20/24 | 15/24 | 10/24 |
| live-tx | 6/8 | 6/8 | 1/8 | 2/8 |
| live-research | 3/5 | 3/5 | 3/5 | 2/5 |
| protocol-current | 2/2 | 2/2 | 1/2 | 0/2 |
| cost-calibration | 1/7 | 1/7 | 0/7 | 0/7 |
| live-read | 0/4 | 0/4 | 0/4 | 0/4 |

Everyone solved 10 tasks. No one solved 15: both ERC-8004 addresses, all
seven cost-calibration tasks except the one Fable/Opus get, all four
live-read tasks, `live-pool-liquidity`, `live-usdc-supply`, `live-nonce`,
and `tx-calldata-permit-2612`.

**Anomalies**

- **Fable dropped 6 tasks vs yesterday, all in one direction (6 down, 0
  up).** Three canonical addresses (`morpho-blue`, `universal-router`,
  `erc8004-reputation`), `live-usdc-supply`, and two calldata tasks. Two of
  the address misses were "no address in the reply" — hedged answers, not
  wrong ones. Sonnet flipped 7 (3 up, 4 down), which looks like noise;
  Fable's 6/0 does not. Difference from yesterday: 12 concurrent claude
  processes instead of 3. Untested hypothesis: load changes the replies.
  Needs a repeat at concurrency 3 before Fable-vs-Opus on this track means
  anything.
- **Run-to-run noise on a 50-task track is about ±3 tasks (6%).** Opus and
  Fable are inside that band of each other. Don't rank them on one run.
- **Points-so-far ranking rewards speed mid-run.** Sonnet led for the
  first minute at 58% accuracy because it answers fastest. Use the
  `accuracy` sort while a run is live; points only mean something at the
  end.
- **The four `live-read` tasks are 0/4 for every model, both days.**
  Current block / gas / ETH price / nonce are unknowable closed-book.
  Mark them `closed_book: false` so the closed track stops carrying dead
  weight (46 live tasks instead of 50).

**Arena checks that passed:** four agents rendered, ranks updated live,
rows re-sorted by points / accuracy / fixed, running cells pulsed yellow,
pass/fail cells green/red, score bars matched the grids, consensus row
filled in as results landed, hover tooltips showed truth vs answer. One
bug found and fixed: a window resize during a finished run reset the
clock to 00:00.

## 2026-09-02 — repeat runs, Haiku exec baseline, live rerun

See `PLAN.md` "Measured 2026-09-02". Live closed-book on 50 tasks: Fable
38, Opus 35, Sonnet 21, Haiku 16. Exec: Fable 32/32 perfect including 5x
repeats on three scenarios; Haiku 6/11 perfect, mean 83, loses every
transaction scenario. Laptop slept mid-sweep, so elapsed times from that
night are not model time.
