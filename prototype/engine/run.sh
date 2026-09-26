#!/bin/zsh
# usage: run.sh OUT.json ROUNDS [server flags...]
PY=${PY:-python3}; S=${SENTI_SOCK:-/tmp/senti-proto.sock}
OUT=$1; ROUNDS=$2; shift 2
rm -f $S decisions.jsonl srv.log
/usr/bin/time -l $PY server.py $S . "$@" > srv.log 2>&1 &
for i in $(seq 1200); do grep -q '^ready' srv.log 2>/dev/null && break; sleep 0.1; done
$PY simulate.py $S ./senti-hook $OUT $ROUNDS ${THINK:-0} > /dev/null
pkill -f "server.py $S"; sleep 1
