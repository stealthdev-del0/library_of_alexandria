#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
INSTALL_DIR="${1:-$HOME/.local/bin}"
TARGET="$INSTALL_DIR/alexandria"
SOURCE="$PROJECT_DIR/bin/alexandria"
MAN_DIR="${2:-$HOME/.local/share/man/man1}"
MAN_SOURCE_DIR="$PROJECT_DIR/man"

mkdir -p "$INSTALL_DIR"
ln -sfn "$SOURCE" "$TARGET"

echo "Installed: $TARGET -> $SOURCE"
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  echo
  echo "Add this directory to your PATH:"
  echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi

if [[ -d "$MAN_SOURCE_DIR" ]]; then
  mkdir -p "$MAN_DIR"
  cp "$MAN_SOURCE_DIR"/loa*.1 "$MAN_DIR"/
  echo "Installed man pages to: $MAN_DIR"

  # Refresh manual page index when available.
  if command -v mandb >/dev/null 2>&1; then
    mandb -q "$HOME/.local/share/man" >/dev/null 2>&1 || true
  fi
fi

if [[ ":${MANPATH:-}:" != *":$HOME/.local/share/man:"* ]]; then
  echo
  echo "If man pages are not found yet, add this to your shell profile:"
  echo "  export MANPATH=\"$HOME/.local/share/man:\$MANPATH\""
fi

echo
echo "Run from anywhere:"
echo "  alexandria"
