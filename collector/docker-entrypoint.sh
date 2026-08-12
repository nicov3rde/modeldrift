#!/bin/sh
# Manages Xvfb directly instead of via xvfb-run - xvfb-run's own X-server
# readiness check (which shells out to xdpyinfo) hangs indefinitely running
# as root in this container (confirmed 2026-08-12: xdpyinfo itself works
# once given the right XAUTHORITY, but xvfb-run's internal wait loop never
# gets past it). Chrome's own connection retry easily tolerates the brief
# window between Xvfb starting and Chrome launching, so no readiness check
# is actually needed here.
set -e
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!
trap "kill $XVFB_PID 2>/dev/null" EXIT
sleep 1
exec "$@"
