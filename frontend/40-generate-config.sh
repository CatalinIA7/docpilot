#!/bin/sh
set -eu

: "${DOCPILOT_API_URL:=http://127.0.0.1:8000}"
export DOCPILOT_API_URL

envsubst '${DOCPILOT_API_URL}' \
  < /usr/share/nginx/html/config.template.js \
  > /usr/share/nginx/html/config.js
