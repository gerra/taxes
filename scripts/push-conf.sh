#!/usr/bin/env bash
# Push nginx vhosts to the server and reload nginx.
# Canonical taxes.gerra.sh + redirect-only taxes.gerra.{kz,london}
# (fintrack pattern: a TLD is skipped unless its cert already exists).
# Usage: scripts/push-conf.sh   (REMOTE=hetzner_gb by default)
set -euo pipefail

REMOTE="${REMOTE:-hetzner_gb}"
CANONICAL="taxes.gerra.sh"
REDIRECT_TLDS=(kz london)
DIR="$(cd "$(dirname "$0")/.." && pwd)/deploy/nginx"

pushed_any=0

push_conf() { # $1 = host name, $2 = local conf file
    local name=$1 file=$2
    if ! ssh "$REMOTE" "test -f /etc/letsencrypt/live/$name/fullchain.pem"; then
        echo "SKIP $name — no certificate. Issue it first (needs DNS record):"
        echo "  ssh $REMOTE 'certbot certonly --nginx -d $name'"
        return
    fi
    scp -q "$file" "$REMOTE:/etc/nginx/sites-available/$name"
    ssh "$REMOTE" "ln -sfn /etc/nginx/sites-available/$name /etc/nginx/sites-enabled/$name"
    echo "pushed $name"
    pushed_any=1
}

push_conf "$CANONICAL" "$DIR/$CANONICAL.conf"

for tld in "${REDIRECT_TLDS[@]}"; do
    name="taxes.gerra.$tld"
    tmp=$(mktemp)
    sed "s/{{TLD}}/$tld/g" "$DIR/taxes.gerra.redirect.tld.conf.template" > "$tmp"
    push_conf "$name" "$tmp"
    rm -f "$tmp"
done

if [ "$pushed_any" = 1 ]; then
    ssh "$REMOTE" "nginx -t && systemctl reload nginx"
    echo "nginx reloaded."
fi
