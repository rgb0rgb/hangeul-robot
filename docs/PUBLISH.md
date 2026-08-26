# Public Publishing Notes

This public folder is intentionally smaller than the private working tree.

Publish this folder to GitHub when these checks pass:

```bash
python3 tools/publish_check.py
python3 -m pytest -q
```

Before pushing, confirm that the repository does not contain:

- `data/*.log`
- `data/*.jsonl`
- `data/console_state.json`
- `data/leases/`
- private robot instances under `install/robots/`
- physical robot adapters
- measured safety/current/temperature values
- customer or commercial collaboration documents

The public version is for simulation, architecture review, and integration discussion.
Validated hardware adapters and operational parameters are maintained separately.

