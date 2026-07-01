"""
Soglia — stage 1: the LLM plug (understanding -> a ColumnMap).

This is the ONLY component that consults a model, and the model is a SWAPPABLE
INPUT, never hardwired. `infer_map` builds a prompt, hands it to an injected
`model_caller`, and compiles whatever JSON comes back into a ColumnMap that the
generalized stage-2 transcriber already knows how to run.

That injection is the whole point: your data-residency decision is simply WHICH
caller you pass.
    - `anthropic_caller`  -> Anthropic's API (needs your key)
    - a local caller       -> a model on your own hardware (nothing leaves)
    - `replay_caller`      -> a saved answer, for offline tests
Everything downstream (transcribe, validate, format, orchestrate) is identical
regardless of the choice.

The model emits DATA (a JSON description), never code. Our deterministic compiler
turns that data into the executable ColumnMap — validating field names and
normalizers, and translating declarative skip/role rules into callables. A model
mistake is therefore contained: it can only produce a map we can validate, and
anything it gets wrong still meets the validator downstream.
"""
import json
import os
import urllib.request

from parser import (ColumnMap, FieldRule, NameSlot, CANON_FIELDS, NORMALIZERS,
                    transcribe)

# --- declarative skip / role rules the model may request -> compiled to callables ---

def _skip_column_not_digit(spec):
    c = spec["column"]
    return lambda row: not (len(row) > c and row[c].strip().isdigit())

def _skip_column_startswith(spec):
    c, pre = spec["column"], spec["prefix"]
    return lambda row: len(row) > c and row[c].strip().startswith(pre)

def _skip_column_empty(spec):
    c = spec["column"]
    return lambda row: not (len(row) > c and row[c].strip())

SKIP_RULES = {
    "column_not_digit": _skip_column_not_digit,
    "column_startswith": _skip_column_startswith,
    "column_empty": _skip_column_empty,
}

def _role_value_equals(spec):
    c, eq, then, els = spec["column"], spec["equals"].upper(), spec["then"], spec.get("else")
    return lambda row: then if (len(row) > c and row[c].strip().upper() == eq) else els

def _role_constant(spec):
    return lambda row: spec["value"]

ROLE_RULES = {
    "value_equals": _role_value_equals,
    "constant": _role_constant,
}


# --- the prompt: the real artifact sent to whatever model -------------------

def build_prompt(sample_rows, max_rows=20):
    rows = sample_rows[:max_rows]
    rows_json = json.dumps(rows, ensure_ascii=False, indent=0)
    fields = ", ".join(CANON_FIELDS)
    norms = ", ".join(NORMALIZERS.keys())
    return f"""You convert a messy hotel rooming-list table into a ColumnMap describing where each field lives. Return STRICT JSON only — no prose, no markdown fences.

The rows below are arrays of cell strings; column indices are 0-based and refer to positions in these arrays:
{rows_json}

Canonical fields you may map (omit any the list does not contain — never invent data): {fields}.
Allowed normalizers (format-only cleaning): {norms}.
  - passthrough: leave as-is. dotted_date: turn 05.12.1984 into 05/12/1984.
  - doc_type_passport: for a passport-NUMBER column, also yields the document TYPE.

Return JSON with these keys:
  "header_rows": integer — how many leading rows to skip before data.
  "name_slots": array — one entry PER PERSON that a single row can contain (a row may list two people). Each entry is either
        {{"combined_column": i, "name_order": "surname_first"|"first_surname"}}   for one "SURNAME Firstname" cell, or
        {{"surname_column": i, "firstname_column": j}}                            for separate columns.
  "fields": object mapping a canonical field to {{"column": i, "normalizer": "..."}}.
  "default_role": a 2-digit Alloggiati code as a string (e.g. "20" membro gruppo, "16" ospite singolo).
  "skip" (optional): {{"rule": "column_not_digit"|"column_startswith"|"column_empty", "column": i, "prefix": "..."}} to drop non-guest rows (headers, footers, held "names pending" rows).
  "role" (optional): {{"rule": "value_equals", "column": i, "equals": "...", "then": "18", "else": "20"}}.
  "review_notes": array of short strings flagging anything a human should check — e.g. a role marker hidden in a name cell ("GUIDE NOWAK", "Ks. ..."), fields the list is missing, merged cells, ambiguous columns.

Map verbatim. Do not guess values. Surface every uncertainty in review_notes."""


# --- compile the model's JSON answer into an executable ColumnMap -----------

def parse_map_json(text):
    """Return (ColumnMap, review_notes). Raises ValueError on an invalid map."""
    s = text.strip()
    if "```" in s:                                   # tolerate fenced output
        s = s.split("```")[1]
        s = s[4:] if s.lower().startswith("json") else s
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    data = json.loads(s[start:end + 1])

    slots = []
    for sl in data.get("name_slots", []):
        if "combined_column" in sl:
            slots.append(NameSlot(combined_column=sl["combined_column"],
                                  name_order=sl.get("name_order", "surname_first")))
        else:
            slots.append(NameSlot(surname_column=sl.get("surname_column"),
                                  firstname_column=sl.get("firstname_column")))

    fields = {}
    for fname, rule in data.get("fields", {}).items():
        if fname not in CANON_FIELDS:
            raise ValueError(f"unknown canonical field: {fname!r}")
        norm = rule.get("normalizer", "passthrough")
        if norm not in NORMALIZERS:
            raise ValueError(f"unknown normalizer: {norm!r}")
        fields[fname] = FieldRule(column=rule.get("column"), normalizer=norm)

    skip_row = None
    skip_desc = ""
    if "skip" in data and data["skip"]:
        spec = data["skip"]
        if spec["rule"] not in SKIP_RULES:
            raise ValueError(f"unknown skip rule: {spec['rule']!r}")
        skip_row = SKIP_RULES[spec["rule"]](spec)
        skip_desc = f"{spec['rule']} col{spec.get('column')}"
        if spec.get("prefix"):
            skip_desc += f' "{spec["prefix"]}"'

    role_rule = None
    if "role" in data and data["role"]:
        spec = data["role"]
        if spec["rule"] not in ROLE_RULES:
            raise ValueError(f"unknown role rule: {spec['rule']!r}")
        role_rule = ROLE_RULES[spec["rule"]](spec)

    cmap = ColumnMap(
        header_rows=data.get("header_rows", 1),
        name_slots=slots,
        fields=fields,
        role_rule=role_rule,
        default_role=data.get("default_role", "20"),
        skip_row=skip_row,
        skip_desc=skip_desc,
    )
    return cmap, data.get("review_notes", [])


def infer_map(sample_rows, model_caller):
    """Stage 1: rows -> (ColumnMap, review_notes), via the injected model."""
    return parse_map_json(model_caller(build_prompt(sample_rows)))


# --- model callers: the swappable plug --------------------------------------

def anthropic_caller(prompt, *, model="claude-sonnet-4-6", api_key=None, max_tokens=2000):
    """Real caller: Anthropic's API. Needs a key. Swap this out for a local model
    if your data-residency decision is to keep everything on your own hardware."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY set. Either provide one, or inject a different "
            "model_caller (e.g. a local model) — that choice IS the data-residency decision.")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": model, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def replay_caller(path):
    """Offline caller: ignore the prompt, return a saved model answer. For tests/demos."""
    with open(path, encoding="utf-8") as f:
        saved = f.read()
    return lambda _prompt: saved
