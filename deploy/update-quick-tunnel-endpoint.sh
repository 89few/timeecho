#!/usr/bin/env bash
set -euo pipefail

: "${ENDPOINT_REPOSITORY:?ENDPOINT_REPOSITORY is required}"
: "${ENDPOINT_DEPLOY_KEY:?ENDPOINT_DEPLOY_KEY is required}"

COMPOSE_DIRECTORY="${COMPOSE_DIRECTORY:-/opt/timeecho/backend}"
ENDPOINT_DIRECTORY="${ENDPOINT_DIRECTORY:-/opt/timeecho/endpoint/repository}"
ENDPOINT_BRANCH="${ENDPOINT_BRANCH:-main}"
export GIT_SSH_COMMAND="ssh -i ${ENDPOINT_DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

url=""
for _ in $(seq 1 60); do
  cd "${COMPOSE_DIRECTORY}"
  container_id="$(docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile tunnel-quick ps -q tunnel-quick 2>/dev/null || true)"
  started_at=""
  if [[ -n "${container_id}" ]]; then
    started_at="$(docker inspect --format '{{.State.StartedAt}}' "${container_id}" 2>/dev/null || true)"
  fi
  if [[ -n "${started_at}" ]]; then
    url="$(
      docker logs --since "${started_at}" "${container_id}" 2>&1 \
        | grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' \
        | tail -1 || true
    )"
  fi
  if [[ -n "${url}" ]]; then
    break
  fi
  sleep 2
done

if [[ -z "${url}" ]]; then
  echo "Quick Tunnel URL was not available within 120 seconds" >&2
  exit 1
fi

if [[ ! -d "${ENDPOINT_DIRECTORY}/.git" ]]; then
  if [[ -e "${ENDPOINT_DIRECTORY}" ]]; then
    echo "Endpoint directory exists but is not a Git repository" >&2
    exit 1
  fi
  git clone --branch "${ENDPOINT_BRANCH}" "${ENDPOINT_REPOSITORY}" "${ENDPOINT_DIRECTORY}"
fi

cd "${ENDPOINT_DIRECTORY}"
git fetch origin "${ENDPOINT_BRANCH}"
git reset --hard "origin/${ENDPOINT_BRANCH}"
current_url="$(python3 -c 'import json, pathlib; p=pathlib.Path("endpoint.json"); print(json.loads(p.read_text()).get("api_base_url", "") if p.exists() else "")')"
if [[ "${current_url}" == "${url}" ]]; then
  exit 0
fi
printf '{"api_base_url":"%s","updated_at":"%s"}\n' "${url}" "$(date -u +%FT%TZ)" > endpoint.json
git add endpoint.json
if git diff --cached --quiet; then
  exit 0
fi
git -c user.name='TimeEcho Server' -c user.email='server@timeecho.invalid' \
  commit -m 'chore: update production endpoint'
git push origin "${ENDPOINT_BRANCH}"
