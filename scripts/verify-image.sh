#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-}"

if [ -z "${REPO_SLUG:-}" ]; then
  echo "Usage: REPO_SLUG=owner/repo $0 <image>" >&2
  exit 2
fi

if [ -z "$IMAGE" ]; then
  echo "Usage: $0 <image>" >&2
  exit 2
fi

echo "Verifying image signature for $IMAGE against repo $REPO_SLUG..."
if docker run --rm gcr.io/projectsigstore/cosign:v2.4.1 verify \
  --certificate-identity "https://github.com/$REPO_SLUG/.github/workflows/ci.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" > /dev/null 2>&1; then
  echo "signature verified"
  exit 0
else
  echo "REFUSING TO DEPLOY: signature verification failed"
  exit 1
fi
