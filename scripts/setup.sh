#!/usr/bin/env bash
# One-command dev setup: venv, dev dependencies, pre-commit hooks, .env template.
# See README.md "Setup" and CONTRIBUTING.md.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
  python3.11 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
pre-commit install

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in your LLM provider API key before running the pipeline."
fi

echo "Setup complete. Activate with: source .venv/bin/activate"
