#!/usr/bin/env bash
# The setup.md server steps against a real sshd, sudo and forced command in a throwaway Ubuntu container, then the
# ops tests under GNU userland. Touches nothing outside the container. From the repo root:
#   docker run --rm -v "$PWD:/src:ro" ubuntu:24.04 bash /src/.github/ops/sshd_e2e.sh
# Checks are single-quoted on purpose: check() evals them after the variables are set, and the probes send
# literal $(...) to prove the server never expands them.
# shellcheck disable=SC2016,SC2034
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends openssh-server openssh-client sudo git python3 python3-pip python3-venv ca-certificates >/dev/null
echo "== tools: $(bash --version | head -1)"

# A fake app checkout: /root/clip-api with a stub docker that answers like the real stack.
mkdir -p /root/repo/clip-api/scripts
cp /src/clip-api/scripts/ops.sh /src/clip-api/scripts/deploy.sh /src/clip-api/scripts/check_migrations.py /root/repo/clip-api/scripts/
mkdir -p /root/repo/clip-api/app/migrations/versions
cp /src/clip-api/app/migrations/versions/*.py /root/repo/clip-api/app/migrations/versions/
git -C /root/repo init -q -b main && git -C /root/repo -c user.email=t@t -c user.name=t add -A
git -C /root/repo -c user.email=t@t -c user.name=t commit -qm one
ln -s /root/repo/clip-api /root/clip-api
cat > /usr/local/bin/docker <<'EOF'
#!/bin/sh
echo "$*" >> /tmp/docker.log
case "$*" in
  *"admin.py stuck"*) ;;
  *"admin.py db-status"*) echo "revision 0007 · latest 0007";;
  *"admin.py ops-status"*) printf 'jobs_running=0\njobs_queued=0\noldest_queued_min=-1\nstalest_heartbeat_min=-1\nlast_claim_min=3\nemail_configured=0\nstripe_configured=1\nstripe_webhook_configured=0\n';;
  "compose ps -q"*) echo "id-$4";;
  *"State.Status"*) echo running;;
  *"State.Health"*) echo healthy;;
esac
EOF
chmod 755 /usr/local/bin/docker

# setup.md step 3a
adduser --system --group --shell /bin/sh --home /home/clipops clipops >/dev/null
install -o root -g root -m 0755 /root/clip-api/scripts/ops.sh /usr/local/sbin/clutchclips-ops
install -d -m 700 /root/backups /var/log/clutchclips-ops
printf 'clipops ALL=(root) NOPASSWD: /usr/local/sbin/clutchclips-ops\n' > /etc/sudoers.d/clutchclips-ops
chmod 440 /etc/sudoers.d/clutchclips-ops && visudo -cf /etc/sudoers.d/clutchclips-ops

# setup.md step 2 + 3b
ssh-keygen -q -t ed25519 -N '' -C clutchclips-actions-deploy -f /tmp/deploy_key
ssh-keygen -q -t ed25519 -N '' -C clutchclips-actions-status -f /tmp/status_key
cp /tmp/deploy_key.pub /tmp/clutchclips_actions_deploy.pub; cp /tmp/status_key.pub /tmp/clutchclips_actions_status.pub
install -d -o root -g root -m 755 /home/clipops/.ssh
opts='restrict,no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding'
{
  printf '%s,command="sudo -n /usr/local/sbin/clutchclips-ops \\"$SSH_ORIGINAL_COMMAND\\"" %s\n' "$opts" "$(cat /tmp/clutchclips_actions_deploy.pub)"
  printf '%s,command="sudo -n /usr/local/sbin/clutchclips-ops status" %s\n' "$opts" "$(cat /tmp/clutchclips_actions_status.pub)"
} > /home/clipops/.ssh/authorized_keys
chmod 644 /home/clipops/.ssh/authorized_keys

mkdir -p /run/sshd && ssh-keygen -A >/dev/null && /usr/sbin/sshd
ssh-keyscan -t ed25519 localhost 2>/dev/null > /tmp/known_hosts
S() { local key=$1; shift; ssh -F /dev/null -T -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/tmp/known_hosts clipops@localhost "$@"; }

fail=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }
out=$(S /tmp/deploy_key status 2>/dev/null) || true
check "deploy key runs status as root via sudo" '[[ "$out" == *"result=ok"* && "$out" == *"email_configured=0"* ]]'
rc=0; S /tmp/deploy_key 'ls /root' >/dev/null 2>&1 || rc=$?
check "arbitrary command refused (exit 64)" '[ "$rc" = 64 ]'
rc=0; S /tmp/deploy_key 'status; touch /tmp/pwned' >/dev/null 2>&1 || rc=$?
check "chained command refused" '[ "$rc" = 64 ] && [ ! -e /tmp/pwned ]'
rc=0; S /tmp/deploy_key 'deploy $(touch /tmp/pwned2)' >/dev/null 2>&1 || rc=$?
check "command substitution never runs" '[ "$rc" = 64 ] && [ ! -e /tmp/pwned2 ]'
rc=0; S /tmp/deploy_key "deploy \"\$(touch /tmp/pwned3)\"" >/dev/null 2>&1 || rc=$?
check "quoted substitution never runs" '[ ! -e /tmp/pwned3 ]'
rc=0; S /tmp/deploy_key >/dev/null 2>&1 </dev/null || rc=$?
check "no command: no shell, usage (exit 64)" '[ "$rc" = 64 ]'
rc=0; ssh -F /dev/null -tt -i /tmp/deploy_key -o BatchMode=yes -o UserKnownHostsFile=/tmp/known_hosts clipops@localhost status >/tmp/tty.out 2>&1 || rc=$?
check "pty refused" 'grep -qi "pty" /tmp/tty.out || ! grep -q "^/dev/pts" /tmp/tty.out'
ssh -F /dev/null -N -L 18022:127.0.0.1:22 -i /tmp/deploy_key -o BatchMode=yes -o UserKnownHostsFile=/tmp/known_hosts clipops@localhost >/tmp/fwd.out 2>&1 &
fwd=$!; sleep 2
tunnel=$(timeout 5 ssh-keyscan -p 18022 127.0.0.1 2>/dev/null || true); kill "$fwd" 2>/dev/null || true; sleep 1
check "port forwarding refused (nothing comes through the tunnel)" '[ -z "$tunnel" ] && grep -q "prohibited" /tmp/fwd.out'
out=$(S /tmp/status_key 'deploy aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' 2>/dev/null) || true
check "status key runs status whatever is asked" '[[ "$out" == *"result=ok"* && "$out" != *"refusing"* ]]'
check "sudo rule allows only the one script" '! sudo -u clipops sudo -n /bin/ls /root >/dev/null 2>&1'
check "clipops cannot edit authorized_keys" '! sudo -u clipops sh -c "echo x >> /home/clipops/.ssh/authorized_keys" 2>/dev/null'
out=$(S /tmp/deploy_key "preflight $(git -C /root/repo rev-parse HEAD)" 2>/dev/null) || true
check "preflight reports the installed copy matches" '[[ "$out" == *"ops_installed=same"* ]]'

echo "== GNU userland: ops tests"
python3 -m venv /tmp/venv >/dev/null && /tmp/venv/bin/pip install -q pytest >/dev/null
cp -r /src/clip-api/tests /tmp/t && mkdir -p /tmp/w/clip-api && cp -r /src/clip-api/scripts /src/clip-api/app /tmp/w/clip-api/ \
  && cp -r /tmp/t /tmp/w/clip-api/tests && mkdir -p /tmp/w/.github && cp -r /src/.github/ops /tmp/w/.github/
rm -f /tmp/w/clip-api/tests/conftest.py   # the app conftest needs the full requirements; these tests do not
useradd -m tester && chown -R tester /tmp/w
sudo -u tester -H git config --global user.email t@t; sudo -u tester -H git config --global user.name t
sudo -u tester -H bash -c 'cd /tmp/w/clip-api && /tmp/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ops_script.py tests/test_deploy_script.py tests/test_check_migrations.py tests/test_opsctl.py 2>&1 | tail -3' || fail=1
exit "$fail"
