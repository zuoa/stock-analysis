#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash fetch_recent_feeds.sh \
    --feeds-file /path/to/feeds.md \
    --output-file /path/to/raw.json \
    --api-host https://example.com \
    [--api-key secret] \
    [--hours 24]
EOF
}

FEEDS_FILE=""
OUTPUT_FILE=""
MP_API_HOST=""
MP_API_KEY="${MP_API_KEY:-}"
HOURS=24
SEEN_IDS_FILE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --feeds-file)
      FEEDS_FILE="${2:-}"
      shift 2
      ;;
    --output-file)
      OUTPUT_FILE="${2:-}"
      shift 2
      ;;
    --api-host)
      MP_API_HOST="${2:-}"
      shift 2
      ;;
    --api-key)
      MP_API_KEY="${2:-}"
      shift 2
      ;;
    --hours)
      HOURS="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

test -n "${FEEDS_FILE}" || { echo "missing --feeds-file" >&2; exit 1; }
test -n "${OUTPUT_FILE}" || { echo "missing --output-file" >&2; exit 1; }
test -n "${MP_API_HOST}" || { echo "missing --api-host" >&2; exit 1; }
test -f "${FEEDS_FILE}" || { echo "feeds file not found: ${FEEDS_FILE}" >&2; exit 1; }
command -v curl >/dev/null || { echo "missing curl" >&2; exit 1; }
command -v jq >/dev/null || { echo "missing jq" >&2; exit 1; }

mkdir -p "$(dirname "${OUTPUT_FILE}")"

CUTOFF_EPOCH="$(date -v-"${HOURS}"H +%s 2>/dev/null || date -d "${HOURS} hours ago" +%s)"
RAW_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${RAW_TMP_DIR}"' EXIT
SEEN_IDS_FILE="${RAW_TMP_DIR}/seen-mp-ids.txt"
: > "${SEEN_IDS_FILE}"

parse_epoch() {
  local raw="${1:-}"
  local normalized=""
  local epoch=""

  test -n "${raw}" || { echo 0; return; }

  normalized="$(printf '%s' "${raw}" | sed -E 's/([+-][0-9]{2}):([0-9]{2})$/\1\2/')"

  for fmt in \
    "%Y-%m-%dT%H:%M:%S%z" \
    "%Y-%m-%dT%H:%M%z" \
    "%Y-%m-%d %H:%M:%S%z" \
    "%Y-%m-%d %H:%M%z" \
    "%Y-%m-%dT%H:%M:%SZ" \
    "%Y-%m-%dT%H:%MZ" \
    "%Y-%m-%d %H:%M:%S" \
    "%Y-%m-%d %H:%M" \
    "%Y/%m/%d %H:%M:%S" \
    "%Y/%m/%d %H:%M" \
    "%Y-%m-%d" \
    "%Y/%m/%d"
  do
    epoch="$(date -j -f "${fmt}" "${normalized}" +%s 2>/dev/null)" && {
      echo "${epoch}"
      return
    }
  done

  epoch="$(date -d "${raw}" +%s 2>/dev/null)" && {
    echo "${epoch}"
    return
  }
  epoch="$(date -d "${normalized}" +%s 2>/dev/null)" && {
    echo "${epoch}"
    return
  }

  echo 0
}

# Read feeds from a dedicated descriptor so loop body commands cannot consume it.
exec 3< "${FEEDS_FILE}"
while IFS= read -r line <&3 || [ -n "${line}" ]; do
  case "${line}" in
    ""|\#*) continue ;;
  esac

  MP_ID="$(printf '%s\n' "${line}" | awk '{print $1}')"
  MP_ID="${MP_ID%,}"
  test -n "${MP_ID}" || continue

  MP_NAME="$(printf '%s\n' "${line}" | sed -E 's/^[^[:space:]]+[[:space:]]*//')"
  if [ "${MP_NAME}" = "${line}" ]; then
    MP_NAME=""
  fi
  MP_NAME="$(printf '%s' "${MP_NAME}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

  if grep -Fqx "${MP_ID}" "${SEEN_IDS_FILE}"; then
    continue
  fi
  printf '%s\n' "${MP_ID}" >> "${SEEN_IDS_FILE}"

  FEED_URL="${MP_API_HOST%/}/feed/${MP_ID}.json"
  OUT_FILE="${RAW_TMP_DIR}/${MP_ID}.json"
  JSONL_FILE="${RAW_TMP_DIR}/${MP_ID}.jsonl"
  FILTERED_FILE="${RAW_TMP_DIR}/${MP_ID}.filtered"

  CURL_ARGS=(-fsSL -H "Accept: application/json")
  if [ -n "${MP_API_KEY}" ]; then
    CURL_ARGS+=(
      -H "Authorization: Bearer ${MP_API_KEY}"
      -H "X-API-Key: ${MP_API_KEY}"
    )
  fi

  if ! curl "${CURL_ARGS[@]}" "${FEED_URL}" -o "${OUT_FILE}"; then
    echo "warning: 拉取失败 ${MP_ID} ${MP_NAME}" >&2
    continue
  fi

  jq -c \
    --arg mpId "${MP_ID}" \
    --arg mpName "${MP_NAME}" \
    --arg feedUrl "${FEED_URL}" '
      def article_list:
        if type == "array" then .
        elif .items? then .items
        elif .articles? then .articles
        elif .entries? then .entries
        elif (.data? | type) == "array" then .data
        elif (.data? | type) == "object" then (.data.items // .data.articles // .data.entries // [])
        else []
        end;

      [
        article_list[]
        | . + {
            mpId: $mpId,
            mpName: $mpName,
            feedUrl: $feedUrl,
            sourceUpdated: (.updated // .publish_time // .published // .pubDate // ""),
            sourceUrl: (.url // .link // .permalink // ""),
            sourceTitle: (.title // .name // ""),
            sourceSummary: (.summary // .description // .excerpt // .digest // "")
          }
      ][]
    ' "${OUT_FILE}" > "${JSONL_FILE}"

  : > "${FILTERED_FILE}"
  while IFS= read -r article_json; do
    UPDATED_RAW="$(printf '%s' "${article_json}" | jq -r '.sourceUpdated // empty')"
    UPDATED_EPOCH="$(parse_epoch "${UPDATED_RAW}")"
    if [ "${UPDATED_EPOCH}" -ge "${CUTOFF_EPOCH}" ] 2>/dev/null; then
      printf '%s\n' "${article_json}" >> "${FILTERED_FILE}"
    fi
  done < "${JSONL_FILE}"
done
exec 3<&-

FILTERED_FILES=()
while IFS= read -r filtered_file; do
  FILTERED_FILES+=("${filtered_file}")
done < <(find "${RAW_TMP_DIR}" -type f -name '*.filtered' | sort)

if [ "${#FILTERED_FILES[@]}" -gt 0 ]; then
  jq -s '.' "${FILTERED_FILES[@]}" > "${OUTPUT_FILE}"
else
  printf '[]\n' > "${OUTPUT_FILE}"
fi
