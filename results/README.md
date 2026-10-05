# Results

- `submissions/`: shared A/B results, one JSON file per run of `tools/ab.py` (schema `callshim-ab/1`). See [docs/AB-TESTING.md](../docs/AB-TESTING.md).
- `local/`: your own runs (git-ignored).

## Schema `callshim-ab/1`

| Field | Meaning |
| --- | --- |
| `model`, `harness`, `server`, `hardware`, `settings` | What was tested, as given on the command line |
| `profile.name`, `profile.sha256` | The profile file used (first 16 hex digits of its hash) |
| `callshim_commit` | The callshim commit the run used |
| `minutes_limit` | Time limit per run |
| `arms.<arm>` | Totals per arm: `runs`, `pass`, `median_wall_s`, `tool_calls_per_run`, `rewritten_per_run` |
| `runs[]` | One row per run: `task`, `arm`, `rep`, `pass`, `wall_s`, `exit`, `commits`, `tool_calls`, `rewritten_calls`, `rewrites_by_transform`, `history_restores`, `tools` |
