#!/bin/bash

# Script to install Git hooks for the project

set -e

# Get the repository root directory
REPO_ROOT=$(git rev-parse --show-toplevel)

echo "Installing Git hooks..."

# Copy pre-commit hook
cp "$REPO_ROOT/scripts/pre-commit" "$REPO_ROOT/.git/hooks/pre-commit"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"

echo "✅ Pre-commit hook installed successfully!"
echo ""
echo "The hook will run the following checks before each commit:"
echo "  • Linting (ruff check)"
echo "  • Formatting (ruff format --check)"
echo "  • Type checking (mypy)"
echo "  • Tests (pytest)"
echo ""
echo "To skip the hook temporarily, use: git commit --no-verify"
