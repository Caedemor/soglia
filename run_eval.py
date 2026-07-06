"""
Soglia — run the stage-1 eval (the campaign side of eval_harness.py).

    python3 run_eval.py                     # DRY (default): plan + exact call
                                            # count a live run would make; no
                                            # calls, no scorecard
    python3 run_eval.py --replay            # free: replay the tracked fixture
                                            # answers (lists that have one)
    python3 run_eval.py --live              # the real thing: needs
                                            # ANTHROPIC_API_KEY; writes dated
                                            # gitignored captures to llm_maps/
    python3 run_eval.py --live --runs 3 --lists park,textmail --label pre-hint

Scorecards land in eval/scorecards/<date>-<label>.{json,md}. The harness
never commits — committing a scorecard is the runner's explicit act (the
repo is the record; PLAN-eval-harness.md). Ad-hoc lists join via
--file/--reader/--expect; anything under real-data/ is REFUSED — the
holdout stays sealed. Exit code: 0 iff every list passes its gates.
"""
import argparse
import os
import sys

from eval_harness import (guard_path, load_expectations, run_corpus,
                          render_md, write_scorecard)
from llm_parser import anthropic_caller, replay_caller
from maps import (read_docx_rows, read_xlsx_rows, read_text_rows,
                  parse_mix18, parse_polish, parse_park_stays,
                  MIX18_DOCX, POLISH_XLSX, PARK_XLSX, TEXTMAIL_TXT,
                  TEXTMAIL_MAP)
from parser import transcribe_with_stays

READERS = {"docx": read_docx_rows, "xlsx": read_xlsx_rows,
           "text": read_text_rows}

# The dev corpus: (reader, path, hand_parse for the bonus parity scorer).
DEV = {
    "mix18": ("docx", MIX18_DOCX, lambda: parse_mix18()),
    "polish": ("xlsx", POLISH_XLSX, lambda: parse_polish()),
    "park": ("xlsx", PARK_XLSX, lambda: parse_park_stays().guests),
    "textmail": ("text", TEXTMAIL_TXT,
                 lambda: transcribe_with_stays(
                     read_text_rows(TEXTMAIL_TXT), TEXTMAIL_MAP).guests),
}


def build_corpus(names, extra_file=None, extra_reader=None, extra_expect=None):
    corpus = []
    for n in names:
        reader, path, hand = DEV[n]
        guard_path(path)
        rows = READERS[reader](path)
        hand_names = [f"{g.cognome} {g.nome}".strip() for g in hand()]
        corpus.append((n, rows, load_expectations(n), hand_names))
    if extra_file:
        guard_path(extra_file)
        import json
        with open(extra_expect) as f:
            exp = json.load(f)
        corpus.append((os.path.splitext(os.path.basename(extra_file))[0],
                       READERS[extra_reader](extra_file), exp))
    return corpus


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--label", default="eval")
    ap.add_argument("--lists", default="all")
    ap.add_argument("--file", help="ad-hoc list file (guarded)")
    ap.add_argument("--reader", choices=READERS, help="for --file")
    ap.add_argument("--expect", help="expectations json for --file")
    args = ap.parse_args()

    names = list(DEV) if args.lists == "all" else args.lists.split(",")
    for n in names:
        if n not in DEV:
            sys.exit(f"unknown list {n!r} (have: {', '.join(DEV)})")

    if args.replay:
        have = [n for n in names
                if os.path.exists(f"llm_maps/{n}.json")]
        skipped = [n for n in names if n not in have]
        if skipped:
            print(f"replay: no fixture for {', '.join(skipped)} — skipped "
                  f"(the textmail fixture is an open item, CLAUDE.md)")
        corpus = build_corpus(have, args.file, args.reader, args.expect)
        factory = lambda name: replay_caller(f"llm_maps/{name}.json")
        card = run_corpus(corpus, factory, runs=1, label=args.label,
                          live=False)
    elif args.live:
        corpus = build_corpus(names, args.file, args.reader, args.expect)
        n_calls = len(corpus) * args.runs
        print(f"LIVE: {len(corpus)} list(s) x {args.runs} run(s) = "
              f"{n_calls} calls to {args.model}")
        factory = lambda name: (
            lambda prompt: anthropic_caller(prompt, model=args.model))
        card = run_corpus(corpus, factory, runs=args.runs, label=args.label,
                          live=True, capture_dir="llm_maps")
    else:
        corpus = build_corpus(names, args.file, args.reader, args.expect)
        print(f"DRY RUN — a live invocation would make "
              f"{len(corpus) * args.runs} calls "
              f"({len(corpus)} list(s) x {args.runs} run(s)) to "
              f"{args.model}.\nLists: "
              + ", ".join(e[0] for e in corpus)
              + "\nAdd --live to run it, --replay for the free fixture "
                "pass.")
        return 0

    path = write_scorecard(card)
    print(render_md(card))
    print(f"scorecard written: {path} (+ .md) — committing it is YOUR act")
    return 0 if card["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
