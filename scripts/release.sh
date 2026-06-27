#!/usr/bin/env bash
set -euo pipefail

# Release script for Obsidian-OpenCode-Knowledge
# Usage: ./scripts/release.sh <version>

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 v1.1.0"
  exit 1
fi

echo "Preparing release $VERSION..."

# Update RELEASE_NOTES.md
sed -i "s/## \[Unreleased\]/## [$VERSION] - $(date +%Y-%m-%d)/" RELEASE_NOTES.md

# Commit release notes
git add RELEASE_NOTES.md
git commit -m "release: prepare $VERSION release notes"

# Create tag
git tag "$VERSION"

echo "Release $VERSION prepared successfully!"
echo "To publish: git push origin main --tags"
