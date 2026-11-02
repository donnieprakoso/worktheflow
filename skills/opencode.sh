#!/usr/bin/env bash
# Link or unlink the wtf skill for OpenCode: ~/.config/opencode/skills/wtf
#
# usage: opencode.sh link|unlink|status
#
# OpenCode also reads ~/.claude/skills/, so claude.sh already makes the skill visible
# to it. This script adds the OpenCode-native location as well.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

case "${1:-}" in
  link|unlink|status) ;;
  *) skill_usage; exit 2 ;;
esac

skill_action "OpenCode" "$HOME/.config/opencode/skills" "$1"
