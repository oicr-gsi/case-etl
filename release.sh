#!/bin/bash

set -euo pipefail

MAIN_BRANCH="main"
PROJECT="Case ETL"

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

# determine version
RELEASE_VERSION=$(date +%Y%m%d)
RELEASES_TODAY=1
git fetch --tags
while git tag --list | grep -c -E "^v${RELEASE_VERSION}$" > /dev/null; do
  RELEASE_VERSION="$(date +%Y%m%d)-$((++RELEASES_TODAY))"
done

# release
echo "Preparing release ${RELEASE_VERSION}..."
git tag -a "v${RELEASE_VERSION}" -m "${PROJECT} v${RELEASE_VERSION} release"
git push origin v${RELEASE_VERSION}

echo "Release completed. Copy this export into your shell before running the deploy scripts:"
echo "export CASE_ETL_VERSION=${RELEASE_VERSION}"
