#!/usr/bin/env bash
# Shared link/unlink logic for the wtf skill. Sourced by claude.sh, kiro.sh, opencode.sh.
#
# The skill source of truth is skills/wtf/ in this repo. Each tool gets a symlink
# that points at it, so edits made here apply everywhere.
#
# Safety rules:
#   - link never overwrites a real file or folder, or a link to something else.
#   - unlink only removes a link that points at this repo's skill.

set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SKILLS_DIR/wtf"

skill_usage() {
  echo "usage: $(basename "$0") link|unlink|status" >&2
}

# $1 = tool name for messages, $2 = skills folder of that tool, $3 = alias name (wtf or wf), $4 = link|unlink|status
skill_action() {
  local label="$1" tool_skills_dir="$2" alias_name="$3" action="$4"
  local target="$tool_skills_dir/$alias_name"

  if [[ ! -f "$SKILL_SRC/SKILL.md" ]]; then
    echo "error: $SKILL_SRC/SKILL.md not found" >&2
    exit 1
  fi

  case "$action" in
    link)
      if [[ -L "$target" ]]; then
        if [[ "$(readlink "$target")" == "$SKILL_SRC" ]]; then
          echo "$label: already linked at $target"
          return 0
        fi
        echo "error: $target links to $(readlink "$target"), not to this skill. Not touching it." >&2
        exit 1
      fi
      if [[ -e "$target" ]]; then
        echo "error: $target exists and is not a link. Not touching it." >&2
        exit 1
      fi
      mkdir -p "$tool_skills_dir"
      ln -s "$SKILL_SRC" "$target"
      echo "$label: linked $target -> $SKILL_SRC"
      ;;

    unlink)
      if [[ -L "$target" && "$(readlink "$target")" == "$SKILL_SRC" ]]; then
        rm "$target"
        echo "$label: unlinked $target"
      elif [[ -e "$target" || -L "$target" ]]; then
        echo "error: $target is not this skill's link. Not touching it." >&2
        exit 1
      else
        echo "$label: nothing to unlink at $target"
      fi
      ;;

    status)
      if [[ -L "$target" && "$(readlink "$target")" == "$SKILL_SRC" ]]; then
        echo "$label: linked ($target)"
      elif [[ -e "$target" || -L "$target" ]]; then
        echo "$label: $target exists but is not this skill's link"
      else
        echo "$label: not linked ($target)"
      fi
      ;;
  esac
}
