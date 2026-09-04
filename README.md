# pr-review

Turns a pull request into an interactive review page: semantic zoom, hover
glosses for syntax, executed value tapes, and a predict-then-reveal probe on
every hunk. Everything runs in a container.

Built for the case where a language model wrote the code and one person has to
review all of it.

## Why

Reading a diff is four simultaneous jobs — decode syntax, simulate execution,
infer intent, place it in the system — and the cost isn't any one of them, it's
holding all four at once and paying a context switch every time you drop one to
service another. Skimming to find "the important parts" is undirected search,
which is the most expensive operation of the lot.

So each job gets its own channel, available on demand, without leaving the page:

| job | channel |
|---|---|
| decode syntax | hover a dotted token → language-level gloss, no repo context |
| simulate execution | value tape: the command was actually run, in both versions |
| infer intent | `1` / `2` / `3` cycle prose ⇄ annotated ⇄ raw diff, position held |
| place in system | hunks ordered by *when the machine runs them*, with stage chips |

Two more affordances that matter more than they look:

- **`?` parks a question.** The failure mode isn't "can't read", it's "curiosity
  fires, you leave the diff, you never come back". Capture it and keep going.
- **Every hunk asks before it tells.** You predict, then press `r`. Where your
  model diverges from the code *is* the bug — that turns review from a vigilance
  task into prediction with feedback.

## Install

```bash
git clone <this repo> ~/repositories/pr-review
cd ~/repositories/pr-review && make image
ln -s "$PWD/bin/pr-review" ~/.local/bin/pr-review
```

Requires docker and bash on the host. Nothing else.

## Use

```bash
# a PR by number (needs the network to reach the remote)
PR_REVIEW_NETWORK=bridge pr-review ~/repositories/dotfiles --pr 6 -o /tmp/r6

# or an explicit ref pair, fully offline
pr-review ~/repositories/dotfiles main my-branch -o /tmp/r6
```

That writes `full.diff`, `changes.txt`, `files.json`, `commits.txt` and
`context.md` into the output directory, with both worktrees live inside the
container. Annotation happens next — see [SKILL.md](SKILL.md) for the protocol
an agent follows to produce `review.json`. Then:

```bash
pr-review <repo> main my-branch -o /tmp/r6 -- \
  trace-review.py --cmd 'zsh -lc true' --watch PATH,MANPATH --out /out/trace.json

python3 scripts/render-review.py /tmp/r6/review.json -o /tmp/r6/review.html
```

`make validate JSON=…` checks structure without rendering. Rendering is pure
stdlib, so it works outside the container too.

### Reading the page

`space`/`j` next · `k` back · `1`/`2`/`3` zoom · `r` reveal · `?` park ·
hover any dotted token. Progress and parked questions persist in `localStorage`,
keyed per repo and PR, so you can abandon a session and resume it.

## Containment

The host contributes exactly two things: a **read-only** bind mount of the repo
and a writable output directory. Inside, the repo is cloned with `--shared`, so
worktrees are cheap and the original is never written to. The container runs as
your uid with `no-new-privileges` and `--network none` by default.

This is load-bearing for `trace-review.py`, which *executes the PR's code* in
both versions to produce value tapes. Tracing an unreviewed, machine-authored
change is exactly the thing you don't want happening on your laptop.

## Layout

```
bin/pr-review               host wrapper — the only thing that runs outside docker
Dockerfile                  python:3.12-slim-bookworm + git + zsh
scripts/entrypoint.sh       container entry; bare invocation drops to a shell
scripts/setup-review.sh     clone, worktrees, diff, files.json
scripts/trace-review.py     xtrace both versions, diff watched vars → trace.json
scripts/render-review.py    review.json → review.html, with validation
templates/review.template.html   generic; never edited per-PR
examples/dotfiles-pr6.json  worked example: 6 hunks, 3 real defects
SKILL.md                    the annotation protocol
```

The split that keeps this maintainable: **the agent writes JSON, never HTML.**
The template is generic and the renderer refuses malformed data — missing
answers, unknown verdicts, a gloss matching no diff line.

## Limits

- Sized for 6–12 annotated hunks. More than that, the PR should have been split.
- Tapes need to be runnable. In an unfamiliar stack they get weaker, and the
  protocol requires saying so in the tape's own disclaimer rather than
  presenting a guess as an observation.
- `localStorage` is per-browser; moving machines loses progress.
- `--pr` needs `PR_REVIEW_NETWORK=bridge`. Ref pairs work offline.
