#!/usr/bin/env bash
set -u

VAULT_DIR="${1:-$HOME/Desktop/我的知识库}"
WIKI_DIR="$VAULT_DIR/wiki"
INDEX_FILE="$WIKI_DIR/index.md"
LINT_SCRIPT="$(dirname "$0")/kb-lint-check.sh"

if [[ ! -d "$WIKI_DIR" ]]; then
  echo "[ERR] wiki directory missing: $WIKI_DIR"
  exit 1
fi

if [[ -x "$LINT_SCRIPT" ]]; then
  echo "== lint =="
  bash "$LINT_SCRIPT" "$VAULT_DIR" || true
  echo ""
fi

echo "== quality metrics =="

mapfile -t wiki_files < <(find "$WIKI_DIR" -maxdepth 3 -type f -name '*.md' | sort)
total=${#wiki_files[@]}
tagged=0
short=0
long=0
empty_frontmatter=0

for f in "${wiki_files[@]}"; do
  [[ "$f" == *"/index.md" ]] && continue
  [[ "$f" == *"/log.md" ]] && continue
  if grep -q '^tags:' "$f"; then
    tagged=$((tagged + 1))
  else
    empty_frontmatter=$((empty_frontmatter + 1))
  fi
  lines=$(wc -l < "$f")
  if (( lines < 10 )); then
    short=$((short + 1))
  elif (( lines > 400 )); then
    long=$((long + 1))
  fi
done

tag_ratio=0
if (( total > 0 )); then
  tag_ratio=$(( tagged * 100 / total ))
fi

echo "wiki_files=$total"
echo "tagged_files=$tagged"
echo "tag_coverage=${tag_ratio}%"
echo "empty_frontmatter=$empty_frontmatter"
echo "short_files=$short"
echo "long_files=$long"
