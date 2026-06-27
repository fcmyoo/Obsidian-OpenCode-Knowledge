#!/usr/bin/env bash
set -u

VAULT_DIR="${1:-$HOME/Desktop/我的知识库}"
WIKI_DIR="$VAULT_DIR/wiki"
INDEX_FILE="$WIKI_DIR/index.md"
JSON_MODE="${KB_LINT_JSON:-0}"

ok() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
err() { printf '[ERR] %s\n' "$1"; }
hr() { printf '\n== %s ==\n' "$1"; }

exit_code=0
json_checks=""
json_warnings=""
json_errors=""
json_append() {
  local item="$1"
  if [[ -z "$json_checks" ]]; then
    json_checks="$item"
  else
    json_checks="$json_checks,$item"
  fi
}
json_warn() {
  local msg="$1"
  local item="$2"
  if [[ -z "$json_warnings" ]]; then
    json_warnings="$item"
  else
    json_warnings="$json_warnings,$item"
  fi
  if [[ "$JSON_MODE" != "1" ]]; then
    warn "$msg"
  fi
}
json_err() {
  local msg="$1"
  local item="$2"
  if [[ -z "$json_errors" ]]; then
    json_errors="$item"
  else
    json_errors="$json_errors,$item"
  fi
  if [[ "$JSON_MODE" != "1" ]]; then
    err "$msg"
  fi
  exit_code=1
}

if [[ ! -d "$VAULT_DIR" ]]; then
  json_err "Vault not found: $VAULT_DIR" '{"check":"vault","status":"error","path":"'"$VAULT_DIR"'"}'
fi
json_append '{"check":"vault","status":"ok","path":"'"$VAULT_DIR"'"}'
ok "Vault: $VAULT_DIR"

if [[ ! -d "$WIKI_DIR" ]]; then
  json_err "wiki directory missing: $WIKI_DIR" '{"check":"wiki_directory","status":"error","path":"'"$WIKI_DIR"'"}'
fi
json_append '{"check":"wiki_directory","status":"ok","path":"'"$WIKI_DIR"'"}'
ok "wiki directory exists"

if [[ ! -f "$INDEX_FILE" ]]; then
  json_err "missing index.md: $INDEX_FILE" '{"check":"index_file","status":"error","path":"'"$INDEX_FILE"'"}'
fi
json_append '{"check":"index_file","status":"ok","path":"'"$INDEX_FILE"'"}'
ok "index.md exists"

wiki_files=()
while IFS= read -r f; do
  [[ -n "$f" ]] && wiki_files+=("$f")
done < <(find "$WIKI_DIR" -maxdepth 3 -type f -name '*.md' | sort)

ok "wiki files found: ${#wiki_files[@]}"

declare -A file_set
for f in "${wiki_files[@]}"; do
  rel="${f#"$WIKI_DIR"/}"
  file_set["$rel"]=1
done

missing_links=0
for f in "${wiki_files[@]}"; do
  rel="${f#"$VAULT_DIR"/}"
  dir="${rel%/*}"
  while IFS= read -r link; do
    [[ -z "$link" ]] && continue
    link="${link#/}"
    [[ -z "$link" ]] && continue
    resolved="$VAULT_DIR"
    case "$link" in
      wiki/*)
        resolved="$VAULT_DIR/$link"
        ;;
      ../*)
        resolved="$VAULT_DIR"
        rel="${link#../}"
        while [[ "$rel" == ../* ]]; do
          resolved="${resolved%/*}"
          rel="${rel#../}"
        done
        resolved="$resolved/$rel"
        ;;
      *)
        resolved="$VAULT_DIR/$dir/$link"
        ;;
    esac
    if [[ -f "$resolved" ]]; then
      :
    else
      warn "broken link in ${rel}: $link"
      missing_links=$((missing_links + 1))
    fi
  done < <(grep -oE '\[[^][]+\]\(([^)]+)\)' "$f" | sed -E 's/.*\]\(([^)]+)\)/\1/' || true)
done

if (( missing_links == 0 )); then
  json_append '{"check":"broken_links","status":"ok"}'
  ok "no broken wiki/relative links detected"
else
  json_err "broken links detected: $missing_links" '{"check":"broken_links","status":"error","count":'"$missing_links"'}'
fi

if [[ -f "$INDEX_FILE" ]]; then
  mapfile -t indexed < <(grep -oE '\[[^][]+\]\(([^)]+)\)' "$INDEX_FILE" | sed -E 's/.*\]\(([^)]+)\)/\1/' | sed 's#^./##' | sort -u || true)
  missing_index=0
  for rel in "${!file_set[@]}"; do
    base="${rel##*/}"
    [[ "$base" == "index.md" || "$base" == "log.md" ]] && continue
    found=0
    for idx in "${indexed[@]}"; do
      if [[ "$idx" == *"$base"* ]]; then
        found=1
        break
      fi
    done
    if (( found == 0 )); then
      warn "possibly missing from index: $rel"
      missing_index=$((missing_index + 1))
    fi
  done
  if (( missing_index == 0 )); then
    ok "index.md appears to cover major wiki files"
    json_append '{"check":"index_coverage","status":"ok"}'
  else
    json_err "index coverage issues: $missing_index" '{"check":"index_coverage","status":"error","count":'"$missing_index"'}'
  fi
fi

raw_links=0
missing_raw=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  base="${f#"$WIKI_DIR"/}"
  dir="${base%/*}"
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    rel="${rel#/}"
    [[ "$rel" != *raw/* ]] && continue
    raw_links=$((raw_links + 1))
    resolved="$VAULT_DIR"
    case "$rel" in
      /*)
        resolved="$rel"
        ;;
      ../*)
        resolved="$VAULT_DIR/${rel#../}"
        ;;
      *)
        resolved="$VAULT_DIR/$dir/$rel"
        ;;
    esac
    if [[ ! -f "$resolved" ]]; then
      warn "missing raw source in $base: $rel"
      missing_raw=$((missing_raw + 1))
    fi
  done < <(grep -oE '\[[^][]+\]\(([^)]+)\)' "$f" | sed -E 's/.*\]\(([^)]+)\)/\1/' || true)
done < <(find "$WIKI_DIR" -maxdepth 3 -type f -name '*.md' | sort)

ok "wiki->raw links checked: $raw_links"
if (( missing_raw == 0 )); then
  ok "no missing raw sources detected"
  json_append '{"check":"raw_links","status":"ok"}'
else
  json_err "missing raw sources detected: $missing_raw" '{"check":"raw_links","status":"error","count":'"$missing_raw"'}'
fi

hr "Orphaned Pages"
orphaned=0
total=0
for f in "${wiki_files[@]}"; do
  base="${f#"$WIKI_DIR"/}"
  [[ "$base" == "index.md" || "$base" == "log.md" ]] && continue
  total=$((total + 1))
  has_inlink=0
  has_outlink=0
  if grep -qE '\]\((\.\.\/\.\.\/)?'"$base"'\)' "$INDEX_FILE" 2>/dev/null; then
    has_inlink=1
  fi
  if grep -qE '\]\([^)]*wiki\/[^)]*\.md\)' "$f" 2>/dev/null; then
    has_outlink=1
  fi
  if (( has_inlink == 0 && has_outlink == 0 )); then
    warn "orphaned page candidate: $base"
    orphaned=$((orphaned + 1))
  fi
done
ok "wiki pages checked for orphan status: $total"
if (( orphaned == 0 )); then
  ok "no orphaned page candidates detected"
  json_append '{"check":"orphaned_pages","status":"ok"}'
else
  json_err "orphaned page candidates detected: $orphaned" '{"check":"orphaned_pages","status":"error","count":'"$orphaned"'}'
fi

hr "Frontmatter Completeness"
required_fields="title source created domain"
frontmatter_total=0
frontmatter_missing=0
for f in "${wiki_files[@]}"; do
  base="${f#"$WIKI_DIR"/}"
  [[ "$base" == "log.md" ]] && continue
  frontmatter_total=$((frontmatter_total + 1))
  missing=""
  for field in $required_fields; do
    if ! grep -qE '^[[:space:]]*'"$field"': ' "$f" 2>/dev/null; then
      missing="$missing $field"
    fi
  done
  if [[ -n "$missing" ]]; then
    warn "frontmatter missing fields in $base:$missing"
    frontmatter_missing=$((frontmatter_missing + 1))
  fi
done
ok "frontmatter files checked: $frontmatter_total"
if (( frontmatter_missing == 0 )); then
  ok "no frontmatter missing fields detected"
  json_append '{"check":"frontmatter","status":"ok"}'
else
  json_err "frontmatter missing fields detected: $frontmatter_missing" '{"check":"frontmatter","status":"error","count":'"$frontmatter_missing"'}'
fi

hr "Tag Convergence"
tag_duplicate_threshold="${KB_TAG_DUPLICATE_THRESHOLD:-2}"
declare -A tag_count
for f in "${wiki_files[@]}"; do
  base="${f#"$WIKI_DIR"/}"
  [[ "$base" == "log.md" ]] && continue
  tags=$(sed -n 's/^[[:space:]]*tags:[[:space:]]*\[\(.*\)\].*/\1/p' "$f" 2>/dev/null | tr -d '"' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -E '^[^[:space:]]+$' || true)
  while IFS= read -r tag; do
    [[ -z "$tag" ]] && continue
    tag_count["$tag"]=$(( ${tag_count["$tag"]:-0} + 1 ))
  done <<< "$tags"
done
tag_duplicates=0
for tag in "${!tag_count[@]}"; do
  count=${tag_count["$tag"]}
  if (( count > tag_duplicate_threshold )); then
    warn "tag appears in multiple files: $tag ($count)"
    tag_duplicates=$((tag_duplicates + 1))
  fi
done
if (( tag_duplicates == 0 )); then
  ok "no excessive tag duplicates detected"
  json_append '{"check":"tag_duplicates","status":"ok"}'
else
  json_err "excessive tag duplicates detected: $tag_duplicates" '{"check":"tag_duplicates","status":"error","count":'"$tag_duplicates"'}'
fi

if [[ "$JSON_MODE" == "1" ]]; then
  printf '{"vault":"%s","issues":[%s],"warnings":[%s],"errors":[%s],"exitCode":%d}\n' \
    "$VAULT_DIR" "$json_checks" "$json_warnings" "$json_errors" "$exit_code"
fi

exit "$exit_code"
