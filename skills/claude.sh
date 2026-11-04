#!/usr/bin/env bash
# Link or unlink the wtf skill for Claude Code, under both names:
# ~/.claude/skills/wtf and ~/.claude/skills/wf
#
# usage: claude.sh link|unlink|status
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

case "${1:-}" in
  link|unlink|status) ;;
  *) skill_usage; exit 2 ;;
esac

skill_action "Claude Code" "$HOME/.claude/skills" "wtf" "$1"
skill_action "Claude Code" "$HOME/.claude/skills" "wf" "$1"
