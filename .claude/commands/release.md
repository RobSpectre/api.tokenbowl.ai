---
description: Run CI, bump version, commit and tag for release
---

You are preparing a new release. Follow these steps in order:

1. **Run the full CI suite**:
   - Run linting: `ruff check .`
   - Run formatting check: `ruff format --check .`
   - Run type checking: `mypy src`
   - Run all tests: `pytest -v`

2. **If all CI checks pass**, proceed with the release:
   - Ask the user what type of version bump they want: major, minor, or patch
   - Read the current version from `pyproject.toml` and `src/token_bowl_chat_server/__init__.py`
   - Calculate the new version number based on their choice
   - Update both files with the new version
   - Ask the user for a brief description of what changed in this release
   - Commit the changes with a message like: "Bump version to X.Y.Z - [description]"
   - Create an annotated git tag: `git tag -a vX.Y.Z -m "Version X.Y.Z - [description]"`
   - Push the commit and tag: `git push origin main && git push origin vX.Y.Z`
   - Tell the user the release is ready and provide the GitHub URL to publish the release

3. **If any CI checks fail**:
   - Report which checks failed
   - Show the errors
   - Do NOT proceed with version bump or tagging
   - Ask the user if they want to fix the issues first

**Important**:
- ONLY bump version and tag if ALL CI checks pass
- ALWAYS run the pre-commit hook validation before finalizing
- Provide a summary at the end with the new version number and next steps
