# Results log

Raw result files are gitignored (`results-live/`, `exec-results/`,
`arena-runs/`). This file is the committed record of what was measured,
when, and what looked off. Newest first.

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
