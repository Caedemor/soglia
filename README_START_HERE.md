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
You should see **ALL GREEN (15/15)**. (On Windows without bash, run instead:
`python build_golden.py` then `python test_tracciato.py`, etc.)

All four real sample lists parse through the one engine: Ukrainian .docx = 39
guests, Polish .xlsx = 48 (+7 legend rows emitted-and-flagged for review),
Italian .xlsx = 23 (+9 held rooms tracked as names_pending stays), text-mail
TSV paste = 47 (+1 held trailer: 2 drivers pending).

## The one honest caveat
The "AI" half of the product — stage 1, where a live model reads a messy document
and produces the column map — HAS run live against the model on three of the four
sample lists, and the deterministic layers proved they catch what it misses (the
record: docs/handoff-rev5.md §2 and §7). The remaining unknown is **breadth**:
four dev lists are not the ~20-list eval set, the text-mail list has never been
through stage 1, and the production model/provider choice is deliberately open.

## What to do now, in Claude Code
1. Open this folder in Claude Code (desktop app, Code tab — no terminal needed).
2. First message:
   *"Initialize a git repository here, make the first commit, then run ./run_tests.sh and show me the result."*
   (If you also created a GitHub account: add *"...then create a private GitHub repo and push it."*)
3. Confirm 15/15 green. Now you have a versioned, backed-up baseline — the thing
   that makes the rot above impossible to repeat.
4. (Done — steps 1–3 and the first live-model comparison are history; the repo
   is versioned, on GitHub, and the §8.5.8 engine is complete.) The real next
   task is breadth: grow the eval set toward ~20 real lists and give the
   text-mail list its stage-1 fixture.

The current-state record is docs/handoff-rev5.md (rev. 4 is frozen history).
This repo is the code those documents describe — runnable, tested, versioned.
