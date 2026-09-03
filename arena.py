#!/usr/bin/env python3
"""Arena: run several agents across the whole suite at once and watch live.

Three subcommands, stdlib only:

  serve   serve arena/index.html + the event logs on http://127.0.0.1:8790
  run     run N agents over the chosen tracks in parallel, appending events
          (REAL MODEL RUNS — needs Austin's ok, same rule as every runner)
  replay  re-emit saved results as if live, for free, to look at the page

Every run is a directory arena-runs/<run>/ holding one append-only
events.jsonl. The page polls that file by byte range, so the same page
works against any static host later — publishing a run is copying a file.

Event lines:
  {"type":"meta","run":..,"t":..,"agents":[{"name","cmd"}],
   "tasks":[{"id","track","cat","max"}]}          first line, once
  {"type":"start","agent":..,"task":..,"t":..}
  {"type":"result","agent":..,"task":..,"score":..,"max":..,
   "pass":..,"elapsed":..,"detail":..,"t":..}
  {"type":"agent_done","agent":..,"t":..}

Usage:
  python3 arena.py serve
  python3 arena.py replay --run demo --agents fable-5,opus-5,sonnet-5,haiku-4.5 --speed 40
  python3 arena.py run --run sep3 --tracks closed,tools,live,exec \\
      --agent fable='claude -p --model fable --dangerously-skip-permissions' \\
      --agent haiku='claude -p --model haiku --dangerously-skip-permissions'
"""
import argparse
import concurrent.futures
import glob
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "arena-runs"
sys.path.insert(0, str(HERE))

# ------------------------------------------------------------------ events

class EventLog:
    def __init__(self, run):
        self.dir = RUNS / run
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        self.lock = threading.Lock()

    def emit(self, **ev):
        ev.setdefault("t", round(time.time(), 3))
        line = json.dumps(ev, separators=(",", ":")) + "\n"
        with self.lock, open(self.path, "a") as f:
            f.write(line)
            f.flush()


# ------------------------------------------------------------------ tasks

def load_track_tasks(tracks):
    """Uniform task list: id, track, cat, max points, plus the raw task."""
    import run_eval
    out = []
    if "closed" in tracks:
        for t in run_eval.load_tasks():
            out.append({"id": t["id"], "track": "closed", "cat": t["category"], "max": 1, "raw": t})
    if "tools" in tracks:
        for t in run_eval.load_tasks(tasks_dir=HERE / "tasks-tools"):
            out.append({"id": t["id"], "track": "tools", "cat": t["category"], "max": 1, "raw": t})
    if "live" in tracks:
        import run_live_eval
        for t in run_live_eval.load_tasks():
            out.append({"id": t["id"], "track": "live", "cat": t["category"], "max": 1, "raw": t})
    if "exec" in tracks:
        for sdir in sorted((HERE / "scenarios").iterdir()):
            spec = sdir / "scenario.json"
            if spec.exists():
                s = json.loads(spec.read_text())
                out.append({"id": sdir.name, "track": "exec", "cat": s.get("track", "exec"),
                            "max": sum(s["grading"]["milestones"].values()), "raw": s})
    return out


def public(t):
    return {k: t[k] for k in ("id", "track", "cat", "max")}


# ------------------------------------------------------------------ run

def run_task(agent, task, seed):
    """One (agent, task) attempt on the right engine. Returns (score, max, detail, extra)."""
    import run_eval
    if task["track"] in ("closed", "tools"):
        target = run_eval.CmdTarget(agent["cmd"])
        r = run_eval.run_one(target, task["raw"], 16000)
        return (1 if r["pass"] else 0), 1, r["detail"][:200], {}
    if task["track"] == "live":
        import run_live_eval
        target = run_eval.CmdTarget(agent["cmd"])
        target.env["RPC_URL"] = os.environ["RPC_URL"]
        r = run_live_eval.run_one(target, task["raw"], "agent")
        return (1 if r["pass"] else 0), 1, r["detail"][:200], {}
    if task["track"] == "exec":
        from harness.run_scenario import run_attempt
        r = run_attempt(task["id"], seed, agent["cmd"], name=f"arena-{agent['name']}", save=True)
        detail = ", ".join(k for k, v in r["milestones"].items() if not v["pass"]) or "all milestones"
        if r["safety_violations"]:
            detail += " | VIOLATION: " + "; ".join(r["safety_violations"])[:150]
        return r["score"], r["max_score"], detail, {"milestones": {
            k: v["pass"] for k, v in r["milestones"].items()}}
    raise ValueError(task["track"])


def run_agent(log, agent, tasks, concurrency, seed):
    def one(task):
        log.emit(type="start", agent=agent["name"], task=task["id"])
        t0 = time.time()
        try:
            score, mx, detail, extra = run_task(agent, task, seed)
            err = False
        except Exception as e:  # noqa: BLE001
            score, mx, detail, extra, err = 0, task["max"], f"ERROR: {str(e)[:200]}", {}, True
        log.emit(type="result", agent=agent["name"], task=task["id"], score=score, max=mx,
                 **{"pass": score == mx and not err}, error=err,
                 elapsed=round(time.time() - t0, 1), detail=detail, **extra)
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(one, tasks))
    log.emit(type="agent_done", agent=agent["name"])


def cmd_run(args):
    agents = []
    for spec in args.agent:
        name, _, cmd = spec.partition("=")
        if not cmd:
            sys.exit(f"--agent needs name=cmd, got {spec!r}")
        agents.append({"name": name, "cmd": cmd})
    tracks = args.tracks.split(",")
    if "live" in tracks:
        import run_live_eval
        run_live_eval.load_env_file()
        if not os.environ.get("RPC_URL"):
            sys.exit("live track needs RPC_URL in .env (Alchemy, never public)")
    tasks = load_track_tasks(tracks)
    if args.limit:
        tasks = tasks[:args.limit]
    log = EventLog(args.run)
    if log.path.exists():
        sys.exit(f"{log.path} exists — pick a new --run name")
    log.emit(type="meta", run=args.run, agents=agents, tasks=[public(t) for t in tasks],
             tracks=tracks, seed=args.seed)
    print(f"arena {args.run}: {len(agents)} agents x {len(tasks)} tasks -> {log.path}")
    threads = [threading.Thread(target=run_agent, args=(log, a, tasks, args.concurrency, args.seed),
                                daemon=True) for a in agents]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    log.emit(type="run_done")
    print("done")


# ------------------------------------------------------------------ replay

def _load_saved(name):
    """Saved rows for an agent name: closed-book results/<name>.json plus, by
    model prefix, results-live/<prefix>-closed.json and exec-results/<prefix>-*."""
    rows = {}
    f = HERE / "results" / f"{name}.json"
    if f.exists():
        for r in json.loads(f.read_text())["tasks"]:
            rows[r["id"]] = {"score": int(bool(r["pass"])), "max": 1, "elapsed": r.get("latency_s", 5),
                             "detail": r.get("detail", "")[:200]}
    prefix = name.split("-")[0]
    f = HERE / "results-live" / f"{prefix}-closed.json"
    if f.exists():
        for r in json.loads(f.read_text())["tasks"]:
            rows[r["id"]] = {"score": int(bool(r["pass"])), "max": 1, "elapsed": r.get("latency_s", 5),
                             "detail": r.get("detail", "")[:200]}
    for d in glob.glob(str(HERE / "exec-results" / f"{prefix}-*-seed1")):
        r = json.loads((Path(d) / "result.json").read_text())
        rows[r["scenario"]] = {"score": r["score"], "max": r["max_score"],
                               "elapsed": r["agent"]["elapsed_s"],
                               "detail": ", ".join(k for k, v in r["milestones"].items() if not v["pass"]) or "all milestones",
                               "milestones": {k: v["pass"] for k, v in r["milestones"].items()}}
    return rows


def cmd_replay(args):
    names = args.agents.split(",")
    saved = {n: _load_saved(n) for n in names}
    for n, rows in saved.items():
        if not rows:
            sys.exit(f"no saved results for {n}")
    tasks = load_track_tasks(["closed", "tools", "live", "exec"])
    common = set.intersection(*(set(r) for r in saved.values()))
    tasks = [t for t in tasks if t["id"] in common]
    log = EventLog(args.run)
    if log.path.exists():
        log.path.unlink()
    log.emit(type="meta", run=args.run, agents=[{"name": n, "cmd": "replay"} for n in names],
             tasks=[public(t) for t in tasks], tracks=["replay"], seed=1)
    print(f"replay {args.run}: {len(names)} agents x {len(tasks)} tasks at {args.speed}x")

    def one_agent(name):
        rows = saved[name]
        sem = threading.Semaphore(args.concurrency)

        def one(task):
            with sem:
                r = rows[task["id"]]
                log.emit(type="start", agent=name, task=task["id"])
                time.sleep(min(r["elapsed"], 600) / args.speed)
                extra = {"milestones": r["milestones"]} if "milestones" in r else {}
                log.emit(type="result", agent=name, task=task["id"], score=r["score"], max=r["max"],
                         **{"pass": r["score"] == r["max"]}, error=False,
                         elapsed=r["elapsed"], detail=r["detail"], **extra)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            list(ex.map(one, tasks))
        log.emit(type="agent_done", agent=name)

    threads = [threading.Thread(target=one_agent, args=(n,), daemon=True) for n in names]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    log.emit(type="run_done")
    print("replay done")


# ------------------------------------------------------------------ serve

class Handler(SimpleHTTPRequestHandler):
    """Serves arena/index.html at /, run logs at /runs/<run>/events.jsonl
    (with Range so the page can tail), and /runs.json."""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.path = "/arena/index.html"
            return super().do_GET()
        if path == "/runs.json":
            runs = []
            for d in sorted(RUNS.glob("*/events.jsonl"), key=lambda p: -p.stat().st_mtime):
                runs.append({"run": d.parent.name, "bytes": d.stat().st_size,
                             "mtime": int(d.stat().st_mtime)})
            body = json.dumps(runs).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/runs/") and path.endswith("/events.jsonl"):
            run = path.split("/")[2]
            f = RUNS / run / "events.jsonl"
            if not f.exists() or "/" in run or ".." in run:
                self.send_error(404)
                return
            data = f.read_bytes()
            start = 0
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes="):
                start = int(rng[6:].split("-")[0] or 0)
            chunk = data[start:]
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{len(data)}/{len(data)}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(chunk)
            return
        self.send_error(404)


def cmd_serve(args):
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"arena at http://127.0.0.1:{args.port}/  (runs in {RUNS})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8790)
    s.set_defaults(fn=cmd_serve)
    r = sub.add_parser("run")
    r.add_argument("--run", required=True, help="run name (new directory under arena-runs/)")
    r.add_argument("--agent", action="append", required=True, help="name=cmd, repeatable")
    r.add_argument("--tracks", default="closed,tools,live,exec")
    r.add_argument("--concurrency", type=int, default=3, help="per agent")
    r.add_argument("--seed", type=int, default=1, help="exec scenario seed")
    r.add_argument("--limit", type=int, help="first N tasks only (smoke test)")
    r.set_defaults(fn=cmd_run)
    p = sub.add_parser("replay")
    p.add_argument("--run", default="replay")
    p.add_argument("--agents", required=True, help="comma list of results/<name>.json basenames")
    p.add_argument("--speed", type=float, default=30.0)
    p.add_argument("--concurrency", type=int, default=4)
    p.set_defaults(fn=cmd_replay)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
