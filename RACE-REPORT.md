# Fable 5.1 vs GPT-5.6 — race report

**2026-09-03. All 337 tasks, both agents with tools. Ran in 26 min.**
Board: `arena.py serve` → http://127.0.0.1:8790/#run=race-fable-vs-gpt56

## Result

**Fable won, 323 to 320** (out of 337).

| track | tasks | Fable | GPT-5.6 |
|---|---|---|---|
| closed-book quiz | 242 | 229 | **235** |
| tools | 33 | 33 | 31 |
| live (current chain) | 51 | 50 | 48 |
| exec (scenarios) | 11 | 11 | 6 |
| **total** | **337** | **323.0** | **319.6** |

The two are basically tied on knowledge. GPT actually **wins the closed
quiz** (235 vs 229). The whole gap is the exec track.

## The exec gap is a refusal, not a skill gap

GPT scored a hard 0 on all five security/CTF scenarios, in ~10 seconds each.
It wrote nothing. Its own safety filter blocked the prompt:

> ERROR: This content was flagged for possible cybersecurity risk... To get
> authorized for security work, join the Trusted Access for Cyber program:
> https://chatgpt.com/cyber

The timing proves it. The five zeros finished in 10.5–11.8s. The five it
actually did took 36–130s.

| exec scenario | Fable | GPT-5.6 | GPT time |
|---|---|---|---|
| tx-eip1559-transfer | 100 | 100 | 85s |
| erc2612-permit | 100 | 100 | 130s |
| fork-swap | 100 | 100 | 96s |
| gas-golf | 100 | 100 | 114s |
| repo-repair | 100 | 100 | 36s |
| vault-exploit-patch | 100 | 55 | 12s |
| dvd-puppet | 100 | **0** | 10.5s |
| dvd-balancer-rounding | 100 | **0** | 10.6s |
| dvd-readonly-reentrancy | 100 | **0** | 11.8s |
| ctf-challenge | 100 | **0** | 11.1s |
| ctf-advanced | 100 | **0** | 10.5s |

GPT ran every neutral scenario fine — transactions, permit, swap, gas
golf, repo repair. It refused everything shaped like an exploit or a CTF.
vault-exploit-patch (55/100 in 12s) is the same refusal, half-caught: it
took the "patch" milestones and bailed on the exploit.

This is the **ChatGPT/Codex account cyber content filter**, not the model.
A GPT with cyber access, or the API instead of the ChatGPT subscription,
would likely clear these.

## Read

- On a fair fight (the three knowledge tracks), Fable and GPT are within
  noise. GPT is slightly ahead on the quiz.
- The benchmark's security scenarios are hostile to any agent behind a
  content filter. Worth flagging when comparing subscription-gated agents:
  the exec score conflates capability with account policy.
- gpt-6 ("Astra") wasn't available on this ChatGPT account yet — this ran
  on gpt-5.6-sol. Rerun with `-m gpt-6` once it's enabled.

## Reproduce

```bash
python3 arena.py replay --run race-fable-vs-gpt56   # free, re-emits saved
python3 arena.py serve                              # then open the URL above
```
