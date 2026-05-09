# Release Workflow

This repo uses three long-lived branches:

- `development` for day-to-day integration work
- `master` for the current stable branch head
- `release` for release tagging

## Initial setup

Set up the local release branch once:

```bash
git switch development
git switch -c release
```

## Creating a release

For each release:

```bash
git switch master
git merge --ff-only development
git switch release
git merge --ff-only development
./scripts/release-tag.sh patch
```

To publish the tag to `origin`:

```bash
./scripts/release-tag.sh patch --push
```

## Release helper behavior

The release helper:

- creates annotated `vMAJOR.MINOR.PATCH` tags
- defaults to tagging from the `release` branch
- refuses dirty worktrees unless `--force-dirty` is passed
- supports `major`, `minor`, `patch`, or an explicit version
- supports `--dry-run` for validation without creating a tag

## Offline image package

To export the project images for transport or offline deploy, use:

```bash
./scripts/docker-save.sh
./scripts/docker-save.sh --tag v1.2.3
```

This creates a folder under `releases/` (for example, `releases/latest` by default, or `releases/v1.2.3` when a tag is supplied) containing:

- `api-<tag>.tar`
- `auth-init-<tag>.tar`
- `web-<tag>.tar`
- `docker-compose.yml`
- `docker/nginx-main.conf`
- `docker/nginx.conf`
- `README.md`

Load the tarballs first (`docker load -i <tarfile>`) before running the generated compose file.

Validation examples:

```bash
bash -n ./scripts/release-tag.sh
./scripts/release-tag.sh patch --dry-run --allow-branch --force-dirty
./scripts/release-tag.sh 1.0.0 --dry-run --allow-branch --force-dirty
```
