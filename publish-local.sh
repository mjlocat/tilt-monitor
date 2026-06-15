#!/usr/bin/env bash
#
# Build the tilt-monitor image for the native architecture (plain `docker build`,
# no buildx/multi-arch) and push it to a private registry.
#
# Usage: ./publish-local.sh <version>      e.g. ./publish-local.sh 1.0.1
#
# Pushes two tags: <registry>/<image>:<version> and <registry>/<image>:latest.
# Override defaults with env vars:
#   REGISTRY   (default: master:5000)
#   IMAGE      (default: tilt-monitor)
set -euo pipefail

REGISTRY="${REGISTRY:-master:5000}"
IMAGE="${IMAGE:-tilt-monitor}"

# Build from the repo root (where this script lives), regardless of cwd.
cd "$(dirname "$0")"

REPO="${REGISTRY}/${IMAGE}"

# Stamp the image with the exact source revision (tag + commits-since + hash),
# surfaced in the dashboard footer via app/version.py.
GIT_DESCRIBE="$(git describe --tags --always --long --dirty)"

echo "Building ${REPO}:latest for the native architecture..."
docker build \
  --build-arg TILT_GIT_DESCRIBE="${GIT_DESCRIBE}" \
  -t "${REPO}:latest" \
  .

echo "Pushing to ${REGISTRY}..."
docker push "${REPO}:latest"

echo "Published ${REPO}:latest"
