# project instructions

- use lowercase comments, simple readable code, no emojis, and no em dashes.
- use bun or bunx for javascript and typescript tooling.
- use uv for python and hf instead of huggingface-cli.
- run commands directly; do not truncate with head, tail, less, or more.
- use lowercase conventional one-line commit messages without signatures or co-authors.
- commit after completing each task.
- state assumptions before non-trivial implementation and invite corrections.
- stop and ask when requirements conflict or are unclear.
- summarize changes made, files not touched, and concerns after modifications.
- work on the current branch; do not create branches or worktrees unless requested.
- do not add unrequested features or documentation, refactor unrelated code, or remove unfamiliar code.
- validate the full pipeline at sub-minute scale before scaling; change only the scale parameter.
- define boundaries and invariants before implementing complex features.
- immediately persist new user constraints in this file and acknowledge them.
- keep the readme short and visually simple, and keep the repository description concise.
- keep the public project in the user's github folder under r0hin/slowverb.
- default to 0.85 speed unless the user overrides it with --speed.
