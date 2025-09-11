# ---------- e2e.sh ----------
#!/usr/bin/env bash
set -euo pipefail

API="http://127.0.0.1:8000"
WEB="http://127.0.0.1:3000"
SUFFIX=$(date +%s | tail -c4)

LECT_USER="lect${SUFFIX}"
LECT_EMAIL="${LECT_USER}@ex.com"
LECT_PASS="Pass@123"

STUD_USER="stud${SUFFIX}"
STUD_EMAIL="${STUD_USER}@ex.com"
STUD_PASS="Secret2!"

echo "==[1/8] Ensure images exist and services are up =="
docker compose up -d automark-ssh automark-api automark-web >/dev/null
sleep 1
curl -fsS ${API}/health | python3 -m json.tool | sed 's/^/[health] /'

echo "==[2/8] Register & login lecturer (${LECT_USER}) =="
curl -fsS -X POST ${API}/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${LECT_USER}\",\"email\":\"${LECT_EMAIL}\",\"password\":\"${LECT_PASS}\",\"role\":\"lecturer\",\"first_name\":\"Lect\",\"last_name\":\"${SUFFIX}\"}" \
| python3 -m json.tool

LECT_TOKEN=$(
  curl -fsS -X POST ${API}/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${LECT_USER}\",\"password\":\"${LECT_PASS}\",\"remember_me\":true}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
)
echo "[lecturer token] ${LECT_TOKEN:0:8}…"

echo "==[3/8] Create a folder (A${SUFFIX}) =="
FOLDER_RESP=$(
  curl -fsS -X POST ${API}/api/v1/folders \
    -H "Authorization: Bearer ${LECT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"A${SUFFIX}\",\"description\":\"e2e\",\"status\":\"published\",\"student_ids\":[]}"
)
echo "$FOLDER_RESP" | python3 -m json.tool
FOLDER_ID=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' <<<"$FOLDER_RESP")
echo "[folder id] $FOLDER_ID"

echo "==[4/8] Register & login student (${STUD_USER}) =="
curl -fsS -X POST ${API}/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${STUD_USER}\",\"email\":\"${STUD_EMAIL}\",\"password\":\"${STUD_PASS}\",\"role\":\"student\",\"first_name\":\"Stud\",\"last_name\":\"${SUFFIX}\"}" \
| python3 -m json.tool

STUD_TOKEN=$(
  curl -fsS -X POST ${API}/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${STUD_USER}\",\"password\":\"${STUD_PASS}\",\"remember_me\":true}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
)
echo "[student token] ${STUD_TOKEN:0:8}…"

echo "==[5/8] Verify SSH user exists inside automark-ssh =="
docker exec automark-ssh id "${STUD_USER}"

echo "==[6/8] Submit to folder (enqueue sandbox) =="
RECV=$(
  curl -fsS -H "Authorization: Bearer ${STUD_TOKEN}" -H "Content-Type: application/json" \
    -d "{\"folder_id\":${FOLDER_ID},\"content\":\"smoke-test\"}" \
    ${API}/api/v1/submissions/receive
)
echo "$RECV" | python3 -m json.tool
SID=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["submission_id"])' <<<"$RECV")
echo "[submission id] $SID"

echo "==[7/8] Poll status until completed/failed =="
for i in {1..20}; do
  OUT=$(curl -fsS -H "Authorization: Bearer ${STUD_TOKEN}" ${API}/api/v1/submissions/${SID})
  STATUS=$(python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"])' <<<"$OUT")
  echo "[poll $i] status=$STATUS"
  echo "$OUT" | python3 -m json.tool
  [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]] && break
  sleep 1
done

echo "==[8/8] Quick web check via nginx =="
curl -sI ${WEB}/ | head -n1
echo "E2E ✅"
# ---------- end e2e.sh ----------
