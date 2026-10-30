#!/bin/sh
# Builds the image (PRD FR-018). Run from anywhere; it works from the repository root.
#   PYTHON_IMAGE=<base image pinned by digest> deploy/build.sh          the product image   credit-intel:<commit>
#   PYTHON_IMAGE=<base image pinned by digest> deploy/build.sh test     the test image      credit-intel-test:<commit> (not the product)
# It builds only from a commit, never from files that differ from one: the manifest of every run records this commit.
set -eu
cd "$(dirname "$0")/.."

: "${PYTHON_IMAGE:?set PYTHON_IMAGE to a base image pinned by digest (name@sha256:...), see docs/RUNBOOK_container.md}"

target=runtime
name=credit-intel
if [ "${1:-}" = "test" ]; then
  target=test
  name=credit-intel-test
fi

# The files that go into the image must be exactly those of HEAD. (Other changes in the working tree, such as a document under review, do not matter.)
if ! git diff --quiet HEAD -- src prompts config tests pyproject.toml uv.lock; then
  echo "files that go into the image differ from HEAD; commit them first" >&2
  exit 1
fi
if [ -n "$(git ls-files --others --exclude-standard -- src prompts config tests pyproject.toml uv.lock)" ]; then
  echo "untracked files in the folders that go into the image; commit or remove them first" >&2
  exit 1
fi

commit=$(git rev-parse HEAD)
echo "building $name:$commit (target $target) from $PYTHON_IMAGE"
docker build --target "$target" --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" --build-arg "BUILD_COMMIT=$commit" -t "$name:$commit" .
echo "CREDIT_INTEL_BUILD_COMMIT=$commit"
