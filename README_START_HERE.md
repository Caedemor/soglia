# START HERE

This is your project, cleaned up and turned into a proper repository. Read this
once, then open the folder in Claude Code.

## What I fixed (vs the files that were floating in chat)
The code had **migration rot** — damage from being carried by hand between chat
sessions, not coding mistakes:

1. **Hardcoded machine paths** (`/mnt/user-data/uploads/...`) → now a relative
   `./data/` folder that works on any computer.
2. **Filenames in `maps.py` didn't match the actual data files** (stray hyphens)
   → reconciled.
3. **The Ukrainian `.docx` had been flattened to plain text** (the Word file was
   lost) → rebuilt as a real Word document from the surviving anonymized table.
4. Added `.gitignore` (so real guest data and the database can never be committed),
   a one-command test runner, and a `CLAUDE.md` so Claude Code understands the
   project every session.

## Proof it works
Run this in the folder:
```
./run_tests.sh
```
You should see **ALL GREEN (12/12)**. (On Windows without bash, run instead:
`python build_golden.py` then `python test_tracciato.py`, etc.)

All four real sample lists parse through the one engine: Ukrainian .docx = 39
guests, Polish .xlsx = 48 (+7 legend rows emitted-and-flagged for review),
Italian .xlsx = 23 (+9 held rooms tracked as names_pending stays), text-mail
TSV paste = 47 (+1 held trailer: 2 drivers pending).

## The one honest caveat
The "AI" half of the product — stage 1, where a live model reads a messy document
and produces the column map — has **only ever been tested against saved answers,
never run live.** That is the real unknown and the most important next piece of
work. The deterministic engine around it is solid; the live extraction is unproven.

## What to do now, in Claude Code
1. Open this folder in Claude Code (desktop app, Code tab — no terminal needed).
2. First message:
   *"Initialize a git repository here, make the first commit, then run ./run_tests.sh and show me the result."*
   (If you also created a GitHub account: add *"...then create a private GitHub repo and push it."*)
3. Confirm 12/12 green. Now you have a versioned, backed-up baseline — the thing
   that makes the rot above impossible to repeat.
4. Then the real first task — running stage 1 against a live model on the four
   sample lists and comparing its column maps to the hand-written ones in
   `maps.py`. That tells you whether the AI boundary actually works before you
   build anything on top of it.

A full design record lives in your handoff document (rev. 4). This repo is the
code that document describes — now runnable, tested, and safe to version.
