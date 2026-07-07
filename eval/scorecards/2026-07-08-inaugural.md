# Stage-1 eval scorecard — 2026-07-08 (inaugural)
LIVE, 2 run(s) per list — verdict: **PASS**

## mix18: PASS
gates: map_valid=ok, recall=ok, held_arithmetic=ok, engine_path=ok
guests 39 (matched 39, extras 0); held 0; flagged 0, unrecognized 0; role 20; completeness complete
coverage: {'sesso': 0, 'data_nascita': 37, 'cittadinanza': 0, 'tipo_documento': 36, 'numero_documento': 36}
hand-map outcome parity: [True, True]
stability: {'runs': 2, 'identical_outcomes': False}

## polish: PASS
gates: map_valid=ok, recall=ok, held_arithmetic=ok, engine_path=ok
guests 54 (matched 48, extras 6); held 0; flagged 6, unrecognized 0; role 20; completeness complete
coverage: {'sesso': 0, 'data_nascita': 46, 'cittadinanza': 0, 'tipo_documento': 0, 'numero_documento': 0}
hand-map outcome parity: [False, False]
stability: {'runs': 2, 'identical_outcomes': False}

## park: PASS
gates: map_valid=ok, recall=ok, held_arithmetic=ok, engine_path=ok
guests 23 (matched 23, extras 0); held 18; flagged 0, unrecognized 0; role 20; completeness awaiting_completion
coverage: {'sesso': 0, 'data_nascita': 0, 'cittadinanza': 0, 'tipo_documento': 0, 'numero_documento': 0}
hand-map outcome parity: [True, True]
stability: {'runs': 2, 'identical_outcomes': False}

## textmail: PASS
gates: map_valid=ok, recall=ok, held_arithmetic=ok, engine_path=ok
guests 47 (matched 47, extras 0); held 2; flagged 0, unrecognized 0; role 16; completeness awaiting_completion
coverage: {'sesso': 0, 'data_nascita': 47, 'cittadinanza': 0, 'tipo_documento': 46, 'numero_documento': 46}
hand-map outcome parity: [True, True]
stability: {'runs': 2, 'identical_outcomes': False}

