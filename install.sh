#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
INSTALL_DIR="${1:-$HOME/.local/bin}"
TARGET="$INSTALL_DIR/alexandria"
SOURCE="$PROJECT_DIR/bin/alexandria"
MAN_DIR="${2:-$HOME/.local/share/man/man1}"
MAN_SOURCE_DIR="$PROJECT_DIR/man"
OS_NAME="$(uname -s)"
INSTALL_DEPS="${LOA_INSTALL_DEPS:-1}"

log() {
  echo "[INFO] $*"
}

warn() {
  echo "[WARN] $*" >&2
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_homebrew() {
  if have_cmd brew; then
    return 0
  fi
  log "Homebrew not found. Installing Homebrew..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi

  if ! have_cmd brew; then
    warn "Homebrew installation failed. Please install Homebrew manually and rerun install.sh."
    return 1
  fi
}

install_ollama() {
  if have_cmd ollama; then
    log "Ollama already installed."
    return 0
  fi

  case "$OS_NAME" in
    Darwin)
      ensure_homebrew
      if brew list --cask ollama >/dev/null 2>&1; then
        log "Ollama cask already present."
      else
        log "Installing Ollama (Homebrew cask)..."
        brew install --cask ollama
      fi
      ;;
    Linux)
      if ! have_cmd curl; then
        warn "curl is required to install Ollama on Linux."
        return 1
      fi
      log "Installing Ollama (official installer)..."
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
    *)
      warn "Unsupported OS for automatic Ollama install: $OS_NAME"
      return 1
      ;;
  esac
}

install_obsidian() {
  if have_cmd obsidian || [[ -d /Applications/Obsidian.app ]]; then
    log "Obsidian already installed."
    return 0
  fi

  case "$OS_NAME" in
    Darwin)
      ensure_homebrew
      if brew list --cask obsidian >/dev/null 2>&1; then
        log "Obsidian cask already present."
      else
        log "Installing Obsidian (Homebrew cask)..."
        brew install --cask obsidian
      fi
      ;;
    Linux)
      if have_cmd flatpak; then
        log "Installing Obsidian via Flatpak..."
        flatpak install -y flathub md.obsidian.Obsidian
      elif have_cmd snap; then
        log "Installing Obsidian via Snap..."
        snap install obsidian --classic
      else
        warn "No supported installer found for Obsidian on Linux (flatpak/snap missing)."
        warn "Please install Obsidian manually, then rerun install.sh."
        return 1
      fi
      ;;
    *)
      warn "Unsupported OS for automatic Obsidian install: $OS_NAME"
      return 1
      ;;
  esac
}

install_dependencies() {
  if [[ "$INSTALL_DEPS" != "1" ]]; then
    log "Dependency installation skipped (LOA_INSTALL_DEPS=$INSTALL_DEPS)."
    return 0
  fi

  if ! have_cmd python3; then
    warn "python3 is required but not found. Please install Python 3 and rerun install.sh."
    return 1
  fi

  log "Checking optional GUI/AI dependencies..."
  install_ollama
  install_obsidian
}

install_dependencies

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
