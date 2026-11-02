#!/usr/bin/env bash
# Link or unlink the wtf skill for Kiro CLI: ~/.kiro/skills/wtf
#
# usage: kiro.sh link|unlink|status
#
# Kiro also needs the skill added to a custom agent's config (.kiro/agents/<agent>.json,
# "resources" field, skill://... URI). This script cannot do that step for you.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

case "${1:-}" in
  link|unlink|status) ;;
  *) skill_usage; exit 2 ;;
esac

skill_action "Kiro" "$HOME/.kiro/skills" "$1"

if [[ "$1" == "link" ]]; then
  echo "Kiro: to use it in a custom agent, add skill://~/.kiro/skills/wtf/SKILL.md to that agent's resources in .kiro/agents/<agent>.json."
fi
