#!/usr/bin/env bash
# Spawn a herdr worktree + pi sub-agent (DeepSeek V4.1 Flash) for a work package.
# Usage: scripts/orchestrate/spawn-wp.sh <wp-id e.g. 1.1> <slug e.g. core-ir-py>
set -euo pipefail
WP="$1"; SLUG="$2"
REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
NAME="wp-${WP//./-}"
BRANCH="wp/${WP}-${SLUG}"
MODEL="${ATOMC_SUBAGENT_MODEL:-deepseek/deepseek-v4.1-flash}"
THINKING="${ATOMC_SUBAGENT_THINKING:-medium}"

json=$(herdr worktree create --cwd "$REPO" --branch "$BRANCH" --base main --label "WP-${WP} ${SLUG}" --no-focus)
PANE=$(jq -r '.result.root_pane.pane_id' <<<"$json")
WT=$(jq -r '.result.worktree.path' <<<"$json")
sleep 1
herdr agent start "$NAME" --kind pi --pane "$PANE" --timeout 60000 -- \
  --provider openrouter --model "$MODEL" --thinking "$THINKING" >/dev/null
herdr agent prompt "$NAME" "You are sub-agent WP-${WP} (${SLUG}) for the atomc project, working in a git worktree on branch ${BRANCH} (this directory: ${WT}). Read docs/plan/briefs/_common.md, then PLAN.md, then docs/plan/briefs/WP-${WP}.md and the contract docs it cites. Execute the brief end to end following its ownership rules and definition of done. Stop and ask if blocked. When finished: write docs/plan/handoffs/WP-${WP}.md, commit, git push -u origin ${BRANCH}, and reply with a 5-line summary." >/dev/null
echo "$NAME pane=$PANE worktree=$WT branch=$BRANCH model=$MODEL"
