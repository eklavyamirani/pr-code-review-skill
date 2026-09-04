#!/usr/bin/env python3
"""Run a command in both worktrees under xtrace and report what differed.

    trace-review.py --cmd 'zsh -lc true' --watch PATH,MANPATH --out trace.json

This is the machinery behind the value tapes. Reading code means simulating it
in your head, which is the expensive part; running it in both versions and
diffing the result removes that job entirely.

Runs inside the container only. The whole point is that the PR's code — which
a model wrote and nobody has read yet — executes somewhere disposable.
"""
import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile

# Neither shell picks PS4 up from the environment for xtrace, so it has to be
# set inside the shell before tracing starts. zsh: %N=script, %i=line.
# bash: BASH_SOURCE/LINENO. Both give a file:line anchor we can join to hunks.
PROLOGUE = {
    "zsh":  "PS4='+%N:%i> '; setopt xtrace; ",
    # Single quotes matter: PS4 must expand per traced line, not at assignment.
    "bash": "PS4='+${BASH_SOURCE}:${LINENO}> '; set -x; ",
}
MARK = "__PR_REVIEW_ENV__"
# Leading '+' repeats with nesting depth, hence \++.
LINE = re.compile(r"^\++(?P<file>[^:]*):(?P<line>\d+)>\s?(?P<cmd>.*)$")


def run(cmd, cwd, shell, watch, timeout):
    """Execute cmd with tracing on, then dump the watched variables."""
    env = dict(os.environ)
    # HOME is redirected so a dotfiles-style command writes into a scratch dir
    # rather than the container's real home.
    home = tempfile.mkdtemp(prefix="trace-home-")
    env["HOME"] = home
    dump = ('; set +x 2>/dev/null; echo "' + MARK + '"; '
            + "; ".join(f'echo "{v}=${{{v}-}}"' for v in watch)) if watch else ""
    script = PROLOGUE[shell] + cmd + dump
    try:
        p = subprocess.run([shell, "-c", script], cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=timeout)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, rc = "", f"timed out after {timeout}s", 124
    finally:
        shutil.rmtree(home, ignore_errors=True)

    steps, seen = [], set()
    for l in err.splitlines():
        m = LINE.match(l)
        if not m:
            continue
        d = m.groupdict()
        key = (d["file"], d["line"], d["cmd"])
        if key in seen:
            continue
        seen.add(key)
        steps.append({"file": d["file"], "line": int(d["line"]), "cmd": d["cmd"]})

    vals, after = {}, out.split(MARK)
    if len(after) > 1:
        for l in after[-1].strip().splitlines():
            if "=" in l:
                k, _, v = l.partition("=")
                vals[k] = v
    # The scratch HOME is noise in a tape; show it as $HOME.
    def tidy(o):
        if isinstance(o, str):
            return o.replace(home, "$HOME")
        if isinstance(o, list):
            return [tidy(x) for x in o]
        if isinstance(o, dict):
            return {k: tidy(v) for k, v in o.items()}
        return o

    steps = tidy(steps)
    vals = tidy(vals)
    return {"rc": rc, "steps": steps, "vars": vals,
            "stdout": after[0] if after else out,
            "stderr_untraced": "\n".join(
                l for l in err.splitlines() if not LINE.match(l))}


def path_delta(base, pr):
    """Describe how a PATH-like variable changed, as ordered entries."""
    b, p = base.split(":") if base else [], pr.split(":") if pr else []
    return {"added": [x for x in p if x not in b],
            "removed": [x for x in b if x not in p],
            "reordered": b != p and sorted(b) == sorted(p),
            "base_first": b[0] if b else None, "pr_first": p[0] if p else None}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cmd", required=True, help="command to run in each worktree")
    a.add_argument("--shell", default="zsh", choices=sorted(PROLOGUE))
    a.add_argument("--watch", default="", help="comma-separated env vars to compare")
    a.add_argument("--base", default="/work/base")
    a.add_argument("--pr", default="/work/pr")
    a.add_argument("--timeout", type=int, default=60)
    a.add_argument("--out", default="/out/trace.json")
    args = a.parse_args()

    watch = [v for v in args.watch.split(",") if v]
    for d in (args.base, args.pr):
        if not pathlib.Path(d).is_dir():
            sys.exit(f"no worktree at {d} — run setup-review.sh first")

    res = {side: run(args.cmd, d, args.shell, watch, args.timeout)
           for side, d in (("base", args.base), ("pr", args.pr))}

    # Key on the expanded command, not file:line — a one-line insertion shifts
    # every line below it, which would report the whole tail as "new".
    bs = {s["cmd"] for s in res["base"]["steps"]}
    report = {
        "cmd": args.cmd, "shell": args.shell,
        "rc": {k: res[k]["rc"] for k in res},
        "new_steps": [s for s in res["pr"]["steps"] if s["cmd"] not in bs],
        "vars": {v: {"base": res["base"]["vars"].get(v, ""),
                     "pr": res["pr"]["vars"].get(v, ""),
                     "changed": res["base"]["vars"].get(v) != res["pr"]["vars"].get(v),
                     **({"delta": path_delta(res["base"]["vars"].get(v, ""),
                                             res["pr"]["vars"].get(v, ""))}
                        if v.endswith("PATH") else {})}
                 for v in watch},
        "stdout": {k: res[k]["stdout"] for k in res},
        "stderr": {k: res[k]["stderr_untraced"] for k in res},
        "steps": {k: res[k]["steps"] for k in res},
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2))

    # Human summary — this is what you paste into a tape while annotating.
    print(f"exit: base={report['rc']['base']} pr={report['rc']['pr']}")
    print(f"{len(report['new_steps'])} step(s) execute only in the PR version")
    for s in report["new_steps"][:12]:
        print(f"  {s['file']}:{s['line']}  {s['cmd'][:96]}")
    for v, d in report["vars"].items():
        if not d["changed"]:
            print(f"{v}: unchanged")
            continue
        if "delta" in d:
            print(f"{v}: +{d['delta']['added']} -{d['delta']['removed']}"
                  f"  first: {d['delta']['base_first']} -> {d['delta']['pr_first']}")
        else:
            print(f"{v}: {d['base']!r} -> {d['pr']!r}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
