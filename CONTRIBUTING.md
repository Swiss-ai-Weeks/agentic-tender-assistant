# Contributing

Workflow for the 3 of us during the hackathon:

1. Run `./scripts/setup.sh` once (installs the venv, dev deps, and the
   `pre-commit` hooks that run `ruff` on every commit — CI runs the same
   checks plus `pytest`, so this catches issues before you open a PR).
2. Create a feature branch off `main`: `git checkout -b feat/<short-description>`
3. Commit small, focused changes.
4. Open a PR into `main` (the template will prompt for track + what changed);
   at least one of the other two reviews before merging.
5. Avoid pushing directly to `main` once there's shared code — merge via PR instead.
6. Keep secrets out of git — use `.env` (gitignored) with `.env.example` as the template.
