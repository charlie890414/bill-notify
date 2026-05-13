#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

SCHEDULE="${BILL_NOTIFY_CRON:-0 10 * * *}"
COMMAND="${BILL_NOTIFY_COMMAND:-/usr/local/bin/bill-notify}"
CRONTAB="${SUPERCRONIC_CRONTAB:-/tmp/bill-notify.crontab}"

printf "%s %s\n" "$SCHEDULE" "$COMMAND" > "$CRONTAB"
echo "bill-notify scheduler started; cron: ${SCHEDULE}; command: ${COMMAND}"

exec supercronic -no-reap "$CRONTAB"
