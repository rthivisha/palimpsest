# Example MBA Cases

This directory contains representative expression seeds and formal verification examples for PALIMPSEST.

## Files

- `sample_mba_cases.json` — benchmark cases for algebraic identities and counterexample-driven repair.

## Suggested usage

```bash
python - <<'PY'
import json
with open('examples/sample_mba_cases.json') as f:
    data = json.load(f)
print(len(data['cases']))
print(data['cases'][0])
PY
```

These examples are intended for local testing, UI demos, and regression validation of the proof loop.
