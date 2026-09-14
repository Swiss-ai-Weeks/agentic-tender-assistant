# Contributing

Workflow for the 3 of us during the hackathon:

1. Create a feature branch off `main`: `git checkout -b feat/<short-description>`
2. Commit small, focused changes.
3. Open a PR into `main`; at least one of the other two reviews before merging.
4. Avoid pushing directly to `main` once there's shared code — merge via PR instead.
5. Keep secrets out of git — use `.env` (gitignored) with `.env.example` as the template.
