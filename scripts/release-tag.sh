#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: release-tag.sh [major|minor|patch|VERSION] [options]

Create a SemVer Git tag that triggers release publishing automation.
By default, releases are tagged from the local release branch and pushed to
origin when --push is used.

Arguments:
  major                   Increment MAJOR and reset MINOR/PATCH
  minor                   Increment MINOR and reset PATCH
  patch                   Increment PATCH
  VERSION                 Use an explicit version, with or without leading v

Options:
  -p, --push              Push the tag to the configured remote after creating it
  -f, --force-dirty       Allow tagging with uncommitted changes
      --allow-branch      Allow tagging from a branch other than the release branch
      --dry-run           Show the tag that would be created without tagging
      --remote REMOTE     Remote to push to when --push is used (default: origin)
      --release-branch BRANCH
                           Branch releases should be tagged from (default: release)
  -m, --message MESSAGE   Annotated tag message
  -h, --help              Show this help

Examples:
  ./scripts/release-tag.sh patch
  ./scripts/release-tag.sh minor --push
  ./scripts/release-tag.sh 1.5.0-rc1
  ./scripts/release-tag.sh v1.4.2 -m "Release v1.4.2"
EOF
}

bump="patch"
push_tag=0
force_dirty=0
allow_branch=0
dry_run=0
remote="origin"
release_branch="release"
message=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        major|minor|patch)
            bump="$1"
            shift
            ;;
        -p|--push)
            push_tag=1
            shift
            ;;
        -f|--force-dirty)
            force_dirty=1
            shift
            ;;
        --allow-branch)
            allow_branch=1
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --remote)
            remote="${2:?missing value for $1}"
            shift 2
            ;;
        --release-branch)
            release_branch="${2:?missing value for $1}"
            shift 2
            ;;
        -m|--message)
            message="${2:?missing value for $1}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            bump="$1"
            shift
            ;;
    esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: this script must be run inside a Git repository" >&2
    exit 1
fi

current_branch="$(git branch --show-current)"
if [[ "$allow_branch" -eq 0 && "$current_branch" != "$release_branch" ]]; then
    if [[ -z "$current_branch" ]]; then
        current_branch="detached HEAD"
    fi

    echo "ERROR: releases should be tagged from '${release_branch}', not ${current_branch}" >&2
    echo "Run 'git switch ${release_branch}' first, or pass --allow-branch." >&2
    exit 1
fi

if [[ "$force_dirty" -eq 0 && -n "$(git status --porcelain)" ]]; then
    echo "ERROR: worktree has uncommitted changes" >&2
    echo "Commit or stash changes first, or pass --force-dirty." >&2
    exit 1
fi

if [[ "$push_tag" -eq 1 && "$dry_run" -eq 0 ]]; then
    if ! git remote get-url "$remote" >/dev/null 2>&1; then
        echo "ERROR: remote does not exist: ${remote}" >&2
        exit 1
    fi
fi

latest_tag="$(
    git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname |
        grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
        head -n 1 || :
)"

if [[ "$bump" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
    version="${bump#v}"
else
    if [[ -z "$latest_tag" ]]; then
        major=0
        minor=0
        patch=0
    else
        version="${latest_tag#v}"
        IFS=. read -r major minor patch <<< "$version"
    fi

    case "$bump" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "ERROR: expected major, minor, patch, or explicit VERSION" >&2
            usage >&2
            exit 2
            ;;
    esac

    version="${major}.${minor}.${patch}"
fi

tag="v${version}"
target_commit="$(git rev-parse --short HEAD)"

if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
    echo "ERROR: tag already exists: ${tag}" >&2
    exit 1
fi

if [[ -z "$message" ]]; then
    message="Release ${tag}"
fi

if [[ "$dry_run" -eq 1 ]]; then
    echo "Would create tag ${tag} at ${target_commit}"
    echo "Message: ${message}"

    if [[ "$push_tag" -eq 1 ]]; then
        echo "Would push tag ${tag} to ${remote}"
    else
        echo "Would not push tag ${tag}"
    fi

    exit 0
fi

git tag -a "$tag" -m "$message"
echo "Created tag ${tag} at ${target_commit}"

if [[ "$push_tag" -eq 1 ]]; then
    git push "$remote" "$tag"
    echo "Pushed tag ${tag} to ${remote}"
else
    echo "Run 'git push ${remote} ${tag}' to publish and trigger release automation."
fi
