#!/usr/bin/env bash
# Mutation proof: a test that claims to pin an implementation must go red when the
# implementation drifts, and green again once restored. This script asserts that, so it
# can gate CI instead of printing a verdict it never checked.
#
# Usage:
#   bash scripts/verify_mutation.sh --test "<pytest command>" --file <path> \
#        --find "<literal anchor>" --replace "<replacement>"
#
# Exit codes: 0 proof held; 1 the baseline or the red run disagreed with the claim;
#             2 usage/anchor/precondition error. The mutated file is always restored,
#             and the restore is verified by sha256 before the script exits.
# NOTE: --test runs through `bash -c`, so quote any path with a space in it
#       (this checkout is "/root/better resume").
set -euo pipefail

TEST_CMD=""
FILE=""
FIND=""
REPLACE=""

usage() {
  sed -n "2,12p" "$0" | sed "s/^# \{0,1\}//"
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --test) TEST_CMD="${2:-}"; shift 2 ;;
    --file) FILE="${2:-}"; shift 2 ;;
    --find) FIND="${2:-}"; shift 2 ;;
    --replace) REPLACE="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

[ -n "$TEST_CMD" ] && [ -n "$FILE" ] && [ -n "$FIND" ] || usage
[ -f "$FILE" ] || { echo "FAIL: --file not found: $FILE" >&2; exit 2; }
grep -qF -- "$FIND" "$FILE" || {
  echo "FAIL: --find anchor not present in $FILE:" >&2
  printf "  %s\n" "$FIND" >&2
  echo "  (the implementation drifted; update this proof or the anchor)" >&2
  exit 2
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BEFORE_SHA="$(sha256sum "$FILE" | cut -d" " -f1)"
BACKUP="$(mktemp)"
cp -- "$FILE" "$BACKUP"

restore() {
  cp -- "$BACKUP" "$FILE"
  rm -f -- "$BACKUP"
  local after
  after="$(sha256sum "$FILE" | cut -d" " -f1)"
  if [ "$after" != "$BEFORE_SHA" ]; then
    echo "FAIL: $FILE was not restored byte-for-byte (sha256 drifted)" >&2
    echo "      before=$BEFORE_SHA" >&2
    echo "      after =$after" >&2
    exit 1
  fi
  echo "restored: $FILE sha256=${BEFORE_SHA:0:16}…"
}
trap restore EXIT INT TERM

echo "== 1/3 baseline: the test must PASS on the untouched implementation =="
if ! bash -c "$TEST_CMD"; then
  echo "FAIL: baseline run failed - the test is red before any mutation" >&2
  exit 1
fi

echo
echo "== 2/3 mutate: apply --find/--replace to $FILE =="
python3 - "$FILE" "$FIND" "$REPLACE" <<'PY'
import sys
from pathlib import Path
path, find, replace = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = path.read_text(encoding="utf-8")
path.write_text(text.replace(find, replace, 1), encoding="utf-8")
print(f"mutated 1 occurrence in {path}")
PY

echo
echo "== 2/3 red: the test must FAIL on the mutated implementation =="
if bash -c "$TEST_CMD"; then
  echo "FAIL: the test stayed green on the mutation - it does not pin this behaviour" >&2
  echo "      anchor: $FIND" >&2
  echo "      replace: $REPLACE" >&2
  exit 1
fi
echo "ok: mutation was caught"

echo
echo "== 3/3 restore: the test must PASS again =="
restore
trap - EXIT
if ! bash -c "$TEST_CMD"; then
  echo "FAIL: the test is still red after restore" >&2
  exit 1
fi

echo
echo "PASS: baseline green -> mutation red -> restored green ($FILE)"
if git -C "$REPO_ROOT" diff --quiet -- "$FILE"; then
  echo "note: $FILE matches HEAD (no working-tree changes)"
else
  echo "note: $FILE still differs from HEAD (pre-existing changes are intact)"
fi
