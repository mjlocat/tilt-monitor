#!/usr/bin/env bash
#
# Build and publish the multi-arch tilt-monitor image to Docker Hub.
#
# Usage: ./publish.sh <version>      e.g. ./publish.sh 1.0.1
#
# Pushes two tags: <image>:<version> and <image>:latest.
# Run `docker login` first. Override defaults with env vars:
#   IMAGE      (default: mjlocat/tilt-monitor)
#   PLATFORMS  (default: linux/amd64,linux/arm64,linux/arm/v7)
set -euo pipefail

IMAGE="${IMAGE:-mjlocat/tilt-monitor}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64,linux/arm/v7}"

if [ $# -ne 1 ]; then
  echo "Usage: $0 <version>   (e.g. $0 1.0.1)" >&2
  exit 1
fi
VERSION="$1"

# Build from the repo root (where this script lives), regardless of cwd.
cd "$(dirname "$0")"

echo "Building ${IMAGE}:${VERSION} (and :latest) for ${PLATFORMS}..."
docker buildx build \
  --platform "${PLATFORMS}" \
  -t "${IMAGE}:${VERSION}" \
  -t "${IMAGE}:latest" \
  --push .

echo "Published ${IMAGE}:${VERSION} and ${IMAGE}:latest"
