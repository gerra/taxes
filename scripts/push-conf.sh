#!/usr/bin/env bash
# Push the nginx vhost to the server and reload nginx.
# Usage: scripts/push-conf.sh   (REMOTE=hetzner_gb by default)
set -euo pipefail

REMOTE="${REMOTE:-hetzner_gb}"
NAME="taxes.gerra.sh"
CONF="$(cd "$(dirname "$0")/.." && pwd)/deploy/nginx/$NAME.conf"

if ! ssh "$REMOTE" "test -f /etc/letsencrypt/live/$NAME/fullchain.pem"; then
    echo "No certificate for $NAME on $REMOTE yet. Issue it first (needs DNS A record):"
    echo "  ssh $REMOTE 'certbot certonly --nginx -d $NAME'"
    exit 1
fi

scp "$CONF" "$REMOTE:/etc/nginx/sites-available/$NAME"
ssh "$REMOTE" "ln -sfn /etc/nginx/sites-available/$NAME /etc/nginx/sites-enabled/$NAME && nginx -t && systemctl reload nginx"
echo "nginx config for $NAME deployed and reloaded."
