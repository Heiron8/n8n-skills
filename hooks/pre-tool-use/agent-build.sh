#!/usr/bin/env bash
# Fires before create_agent / mutate_agent. First-class Agents are JSON, not
# SDK code, and carry traps the build tools don't flag (missing memory block,
# unpublished sub-agents), so route to the Agents skill first.
exec "$(dirname "$0")/_emit.sh" "agents" \
"Before building an Agent: invoke n8n-agents-official via the Skill tool (memory block, approvals, publish rules)."
