#!/usr/bin/env bash
# Compare end-to-end audio capture latency: legacy WAV upload vs compressed (MP3) upload.
# End-to-end = POST /captures ... until the capture's transcript exists (upload + ingest transcode
# + queue + transcription round-trip). Run against a dev stack: ./scripts/bench-audio-e2e.sh [runs]
set -euo pipefail
API="${API:-http://localhost:8010}"
RUNS="${1:-3}"
TOK=$(curl -s -X POST "$API/api/v1/auth/dev-login" -H 'Content-Type: application/json' \
  -d '{"persona":"doctor","tier":"pro"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['accessToken'])")

WORK=$(mktemp -d)
# Source: the T01 master from the durable fixtures bucket (via the main backend's MinIO container).
docker exec engram-infra-minio-1 sh -c \
  "cat /data/engram-eval-fixtures/model-compare/transcription/T01.wav/xl.meta > /dev/null 2>&1" || true
# Simpler + robust: pull through MinIO client inside the backend container.
docker exec engram-main-backend-1 python -c "
from app.storage.object_store import ObjectStore
s = ObjectStore()
data = s._client.get_object('engram-eval-fixtures', 'model-compare/transcription/T01.wav').read()
open('/tmp/t01.wav','wb').write(data); print(len(data))
" > /dev/null
docker cp engram-main-backend-1:/tmp/t01.wav "$WORK/t01.wav"
ffmpeg -y -loglevel error -i "$WORK/t01.wav" -ac 1 -ar 16000 -b:a 32k "$WORK/t01.mp3"
ls -l "$WORK" | awk '{print $5, $9}'

bench() { # $1=file $2=mime $3=label
  local total=0
  for i in $(seq 1 "$RUNS"); do
    local cid="bench-$3-$i-$RANDOM"
    local t0=$(python3 -c 'import time; print(time.time())')
    local cap=$(curl -s -X POST "$API/api/v1/captures" -H "Authorization: Bearer $TOK" \
      -F "capture_type=audio" -F "new_session=true" -F "client_capture_id=$cid" \
      -F "file=@$1;type=$2" | python3 -c "import json,sys
d=json.load(sys.stdin); print(d['item']['id'] if 'item' in d else d.get('detail'))")
    while :; do
      local done=$(curl -s "$API/api/v1/captures/$cap" -H "Authorization: Bearer $TOK" \
        | python3 -c "import json,sys
d=json.load(sys.stdin); m=d.get('metadata') or {}
t=m.get('transcript'); print(1 if (t and (t.get('text') if isinstance(t,dict) else t)) else 0)")
      [ "$done" = "1" ] && break; sleep 1
    done
    local dt=$(python3 -c "import time; print(f'{time.time()-$t0:.1f}')")
    echo "  $3 run $i: ${dt}s"; total=$(python3 -c "print($total+$dt)")
  done
  echo "$3 mean: $(python3 -c "print(f'{$total/$RUNS:.1f}s')")"
}

echo "== legacy WAV path =="; bench "$WORK/t01.wav" audio/wav wav
echo "== compressed MP3 path =="; bench "$WORK/t01.mp3" audio/mpeg mp3
rm -rf "$WORK"
echo "Note: on localhost the upload leg is ~free — the real-world gap scales with your mobile uplink"
echo "(WAV ~1.92 MB/min vs MP3 ~0.24 MB/min). Add 'tc'/network throttling or run against production"
echo "over mobile data to see the field difference; the worker->gateway leg change shows in both."
