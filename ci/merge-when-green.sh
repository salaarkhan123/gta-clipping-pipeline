#!/bin/bash
# Merge a PR only when CI passed on its exact head commit. Use after the owner approved the merge.
# Usage: ci/merge-when-green.sh <pr-number> <approved-commit-sha>
#
# Prefers GitHub-hosted Check Runs named `test` and `docker-build` (deploy gate / .github/ops/config.json).
# Falls back to local-ci/test and local-ci/docker-build commit statuses when hosted runs are absent.
# Refuses when: the head is not the approved commit; required checks are not success; or any GitHub check
# that actually ran on it failed. A hosted job GitHub never started (billing / spending limit: no step ran)
# is not a test result and does not block on its own — but then local-ci (or a real hosted run) is still required.
set -euo pipefail
pr="${1:?usage: ci/merge-when-green.sh <pr> <sha>}"; want="${2:?approved commit sha}"
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
head="$(gh pr view "$pr" --json headRefOid --jq .headRefOid)"
[[ "$head" == "$want"* ]] || { echo "#$pr head is ${head:0:8}, not the approved ${want:0:8}: NOT MERGED"; exit 1; }

hosted_ok=1
for name in test docker-build; do
  # Latest completed run for this job name; empty → missing.
  st="$(gh api "repos/$REPO/commits/$head/check-runs?filter=latest&per_page=100" \
    --jq "[.check_runs[] | select(.name==\"$name\")][0] | .conclusion // \"missing\"")"
  if [ "$st" != success ]; then
    hosted_ok=0
    hosted_detail="${hosted_detail:-}$name=$st "
  fi
done

if [ "$hosted_ok" -eq 1 ]; then
  echo "#$pr hosted test + docker-build success on ${head:0:8}"
else
  echo "#$pr hosted checks incomplete (${hosted_detail:-}); trying local-ci statuses"
  for ctx in local-ci/test local-ci/docker-build; do
    st="$(gh api "repos/$REPO/commits/$head/statuses" --jq "[.[] | select(.context==\"$ctx\")][0].state // \"missing\"")"
    [ "$st" = success ] || { echo "#$pr $ctx is $st on ${head:0:8}: NOT MERGED"; exit 1; }
  done
fi

for id in $(gh api "repos/$REPO/commits/$head/check-runs?filter=latest&per_page=100" \
  --jq '.check_runs[] | select(.conclusion=="failure" or .conclusion=="timed_out" or .conclusion=="action_required") | .id'); do
  steps="$(gh api "repos/$REPO/actions/jobs/$id" --jq '.steps | length' 2>/dev/null || echo 1)"
  notes="$(gh api "repos/$REPO/check-runs/$id/annotations" --jq '.[].message' 2>/dev/null || true)"
  if [ "$steps" = 0 ] && grep -q "was not started because recent account payments have failed or your spending limit" <<<"$notes"; then
    echo "check run $id never started (GitHub billing); not a test result"
    continue
  fi
  echo "#$pr has a failed GitHub check (run $id) on ${head:0:8}: NOT MERGED"; exit 1
done

gh pr merge "$pr" --merge --match-head-commit "$head"
gh pr view "$pr" --json state,mergeCommit --jq '"#'"$pr"' \(.state) \(.mergeCommit.oid[0:8])"'
