#!/bin/bash

set -euo pipefail

MAIN_BRANCH="main"
PROJECT="Case ETL"

BUMP_TYPE=""

# validate arguments
usage_error() {
  echo "Error: bad arguments" >&2
  echo "Usage: $0 {major|minor|patch}" >&2
  exit 3
}

if [[ "$#" -eq 1 ]]; then
  case "$1" in
    "major")
      BUMP_TYPE="major"
      ;;
    "minor")
      BUMP_TYPE="minor"
      ;;
    "patch")
      # We should be on a x.y.z.dev1 version, where z is already the next patch version
      BUMP_TYPE="stable"
      ;;
    *)
      usage_error
      ;;
    esac
else
  usage_error
fi

# validate git state
if [[ ! $(git branch | grep \* | cut -d ' ' -f2) = "${MAIN_BRANCH}" ]]; then
  echo "Error: Not on ${MAIN_BRANCH} branch" >&2
  exit 1
fi
git fetch
if (( $(git log HEAD..origin/${MAIN_BRANCH} --oneline | wc -l) > 0 )); then
  echo "Error: Branch is not up-to-date with remote origin" >&2
  exit 2
fi

# update version
uv version --bump "${BUMP_TYPE}"
RELEASE_VERSION=$(uv version --short)

# release
echo "Preparing release ${RELEASE_VERSION}..."
git commit -a -m "${PROJECT} v${RELEASE_VERSION} release"
git tag -a "v${RELEASE_VERSION}" -m "${PROJECT} v${RELEASE_VERSION} release"

# update to dev version
uv version --bump patch --bump dev
git commit -a -m "prepared for next development iteration"

git push origin main
git push origin v${RELEASE_VERSION}

echo "Release completed. Copy this export into your shell before running the deploy scripts:"
echo "export CASE_ETL_VERSION=${RELEASE_VERSION}"
