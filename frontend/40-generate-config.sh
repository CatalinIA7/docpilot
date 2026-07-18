#!/bin/sh
set -eu

: "${DOCPILOT_API_URL:=http://127.0.0.1:8000}"

case "$DOCPILOT_API_URL" in
  http://*|https://*) ;;
  *)
    echo "DOCPILOT_API_URL must use http:// or https://" >&2
    exit 1
    ;;
esac

if printf '%s' "$DOCPILOT_API_URL" | LC_ALL=C grep -q '[[:cntrl:]]'; then
  echo "DOCPILOT_API_URL must not contain control characters" >&2
  exit 1
fi

escaped_api_url=$(printf '%s' "$DOCPILOT_API_URL" | sed 's/[\\&|"]/\\&/g')
sed "s|__DOCPILOT_API_URL__|$escaped_api_url|g" \
  /usr/share/nginx/html/config.template.js \
  > /usr/share/nginx/html/config.js
