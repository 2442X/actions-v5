#!/usr/bin/env bash
set -euo pipefail

REPO="2442X/actions-v5"
BRANCH="main"
DEST=".github/workflows"

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "This is not a GitHub repository." >&2; exit 1; }
cd "$ROOT"

exec 3</dev/tty || { echo "No compatible terminal found." >&2; exit 1; }

echo "Fetching file list from $REPO..."
FILES=()
while IFS= read -r p; do FILES+=("$p"); done < <(
  curl -fsSL "https://api.github.com/repos/$REPO/git/trees/$BRANCH?recursive=1" \
    | grep -o '"path": *"[^"]*"' | sed 's/.*: *"\(.*\)"/\1/' \
    | grep -E '^(common|cpp|python)/[^/]+$'
)
[ "${#FILES[@]}" -gt 0 ] || { echo "No files found." >&2; exit 1; }

echo
i=1
for f in "${FILES[@]}"; do printf "  %2d) %s\n" "$i" "$f"; i=$((i+1)); done
echo
read -r -u 3 -p "Numbers to install (e.g. 1 3 5), 'all', or 'q' to quit: " CHOICE

case "$CHOICE" in
  q|Q|"") echo "Cancelled."; exit 0 ;;
  all)    SEL=$(seq 1 "${#FILES[@]}") ;;
  *)      SEL=${CHOICE//,/ } ;;
esac

mkdir -p "$DEST"
for n in $SEL; do
  [[ "$n" =~ ^[0-9]+$ ]] && (( n >= 1 && n <= ${#FILES[@]} )) || { echo "Skipping invalid choice: $n"; continue; }
  f="${FILES[$((n-1))]}"
  out="$DEST/$(basename "$f")"
  if [ -e "$out" ]; then
    read -r -u 3 -p "$out exists. Overwrite? [y/N] " a
    [[ "$a" =~ ^[Yy]$ ]] || { echo "Kept $out"; continue; }
  fi
  curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/$f" -o "$out" && echo "Installed $out"
done

echo "Done!"
