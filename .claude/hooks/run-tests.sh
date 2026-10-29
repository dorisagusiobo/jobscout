#!/bin/bash
# Runs JobScout's tests after Claude Code edits a Python file.

# Claude Code sends details of the edit as JSON on stdin; pull out the file path.
file=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')

# Only react to Python files; edits to docs or Terraform don't need the test suite.
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Run the tests. On failure, send the last lines to Claude (stderr) and exit 2
# so Claude Code shows Claude the failure and it has to deal with it.
if ! output=$(uv run pytest -q 2>&1); then
  echo "Tests failed after editing $file:" >&2
  echo "$output" | tail -20 >&2
  exit 2
fi
exit 0