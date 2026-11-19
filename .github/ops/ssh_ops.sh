#!/usr/bin/env bash
# Run one ops.sh request on the production server and keep its key=value output.
#
#   .github/ops/ssh_ops.sh <name> <request words...>      e.g.  ssh_ops.sh preflight preflight <sha>
#
# Env: PROD_SSH_KEY, PROD_HOST, PROD_KNOWN_HOSTS (environment secrets), PROD_SSH_USER (default clipops),
#      PROD_SSH_PORT (default 22), OPS_DIR (where <name>.env, .rc and .sec go).
# The host key is pinned: StrictHostKeyChecking=yes against PROD_KNOWN_HOSTS only. The key and known_hosts are
# written to a private temp dir and removed on exit; neither is printed. The server's forced command decides what
# actually runs; this script only sends the request string.
set -euo pipefail
name=${1:?name}
shift
[[ "$name" =~ ^[a-z_]+$ ]] || { echo "bad name" >&2; exit 64; }
: "${PROD_SSH_KEY:?PROD_SSH_KEY is not set (environment secret)}"
: "${PROD_HOST:?PROD_HOST is not set (environment secret)}"
: "${PROD_KNOWN_HOSTS:?PROD_KNOWN_HOSTS is not set (environment secret)}"
: "${OPS_DIR:?OPS_DIR is not set}"
mkdir -p "$OPS_DIR"

umask 077
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf '%s\n' "$PROD_SSH_KEY" > "$tmp/key"
printf '%s\n' "$PROD_KNOWN_HOSTS" > "$tmp/known_hosts"

start=$(date +%s)
rc=0
ssh -F /dev/null -T -i "$tmp/key" -p "${PROD_SSH_PORT:-22}" \
  -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$tmp/known_hosts" -o GlobalKnownHostsFile=/dev/null \
  -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=10 -o LogLevel=ERROR \
  "${PROD_SSH_USER:-clipops}@$PROD_HOST" "$*" > "$tmp/out" || rc=$?

grep -E '^[a-z][a-z0-9_]*=[^[:cntrl:]]*$' "$tmp/out" | cut -c1-500 > "$OPS_DIR/$name.env" || true
echo "$rc" > "$OPS_DIR/$name.rc"
echo $(( $(date +%s) - start )) > "$OPS_DIR/$name.sec"
echo "--- $name: exit $rc in $(cat "$OPS_DIR/$name.sec")s"
cat "$OPS_DIR/$name.env"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  cat "$OPS_DIR/$name.env" >> "$GITHUB_OUTPUT"
  echo "rc=$rc" >> "$GITHUB_OUTPUT"
fi
exit "$rc"
