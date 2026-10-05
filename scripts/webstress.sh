#!/usr/bin/env bash
# Compatibility entrypoint for existing launch commands.
set -eo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/breakingweb.sh" "$@"
