#!/bin/bash
# Compatibility wrapper for the current Raspberry Pi setup flow.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Delegating to setup_pi5.sh"
exec bash "$SCRIPT_DIR/setup_pi5.sh" "$@"