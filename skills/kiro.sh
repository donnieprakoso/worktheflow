#!/usr/bin/env bash
# Link or unlink the wtf skill for Kiro CLI, under both names:
# ~/.kiro/skills/wtf and ~/.kiro/skills/wf
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

skill_action "Kiro" "$HOME/.kiro/skills" "wtf" "$1"
skill_action "Kiro" "$HOME/.kiro/skills" "wf" "$1"

if [[ "$1" == "link" ]]; then
  echo "Kiro: to use it in a custom agent, add skill://~/.kiro/skills/wtf/SKILL.md (or .../wf/SKILL.md) to that agent's resources in .kiro/agents/<agent>.json."
fi
