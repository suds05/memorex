#!/usr/bin/env bash
######################################################################
#
# Bootstrap script for running the memoir CLI.
#
# This script creates a local virtual environment, installs the memoir
# package in editable mode, checks OpenAI credentials, and launches the CLI.
#
# Author: Sudhakar Narayanamurthy.
#

set -euo pipefail

# Easy local runtime settings. Values already exported in your shell win.
: "${OPENAI_MODEL:=gpt-5.4-mini}"
: "${MEMOIR_DATA_DIR:=${HOME}/.memorex}"
: "${MEMOIR_DEBUG:=1}"
# Uncomment to disable ANSI color in debug output.
# : "${NO_COLOR:=1}"
export OPENAI_MODEL MEMOIR_DATA_DIR MEMOIR_DEBUG

# Resolve the repository root from this script's location.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# Require Python 3 before trying to create a virtual environment.
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found on PATH." >&2
  exit 1
fi

# Ubuntu/Debian split venv support into a separate package.
if ! python3 -c "import venv" >/dev/null 2>&1; then
  echo "Python venv support is missing." >&2
  echo "On Ubuntu/Debian, install it with:" >&2
  echo "  sudo apt update && sudo apt install python3.12-venv" >&2
  exit 1
fi

# venv creation also needs ensurepip so pip can be bootstrapped inside .venv.
if ! python3 -m ensurepip --version >/dev/null 2>&1; then
  echo "Python ensurepip support is missing, so a usable .venv cannot be created." >&2
  echo "On Ubuntu/Debian, install it with:" >&2
  echo "  sudo apt update && sudo apt install python3.12-venv" >&2
  echo "Then rerun:" >&2
  echo "  ./run.sh" >&2
  exit 1
fi

# Refuse to continue if a previous failed venv creation left a partial directory.
if [ -d "${VENV_DIR}" ] && [ ! -f "${VENV_DIR}/bin/activate" ]; then
  echo "Found an incomplete virtual environment at ${VENV_DIR}." >&2
  echo "After installing python3.12-venv, remove it and rerun:" >&2
  echo "  rm -rf \"${VENV_DIR}\"" >&2
  echo "  ./run.sh" >&2
  exit 1
fi

# Create the local virtual environment once and reuse it on later runs.
if [ ! -d "${VENV_DIR}" ]; then
  if ! python3 -m venv "${VENV_DIR}"; then
    echo "Failed to create the virtual environment." >&2
    echo "On Ubuntu/Debian, install venv support with:" >&2
    echo "  sudo apt update && sudo apt install python3.12-venv" >&2
    echo "Then remove any partial .venv and rerun ./run.sh." >&2
    exit 1
  fi
fi

# Activate the local virtual environment for dependency installation and runtime.
source "${VENV_DIR}/bin/activate"

# Install the project and its dependencies into the local virtual environment.
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e "${SCRIPT_DIR}"

# Refuse to start the LLM-backed CLI without an API key.
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "OPENAI_API_KEY is not set. Export it before running this script." >&2
  exit 1
fi

# Replace the shell process with the memoir CLI.
exec python -m memoir
