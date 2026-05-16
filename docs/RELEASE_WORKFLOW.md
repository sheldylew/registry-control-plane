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

For each release, start from a clean `development` branch and run the Docker-backed gate before promoting branch heads:

```bash
git switch development
ALLOW_DEV_DEFAULT_CREDENTIALS=1 ./scripts/e2e-test.sh

git switch master
git merge --ff-only development
git push origin master

git switch release
git merge --ff-only development
git push origin release
```

Create and publish the release tag from `release` in one helper invocation:

```bash
./scripts/release-tag.sh patch --push
```

If you create a tag without `--push`, publish that exact tag with `git push origin vX.Y.Z`. Do not rerun `./scripts/release-tag.sh patch --push` afterward; that would calculate and create the next patch tag.

## Release helper behavior

The release helper:

- creates annotated `vMAJOR.MINOR.PATCH` tags
- defaults to tagging from the `release` branch
- refuses dirty worktrees unless `--force-dirty` is passed
- supports `major`, `minor`, `patch`, or an explicit version
- supports `--push` to push the newly created tag to the configured remote
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
- `nginx-<tag>.tar`
- `docker-compose.yml`
- `rcp`
- `README.md`

Load the tarballs first (`docker load -i <tarfile>`), then use `./rcp up` or run the generated compose file directly.

Validation examples:

```bash
bash -n ./scripts/release-tag.sh
./scripts/release-tag.sh patch --dry-run --allow-branch --force-dirty
./scripts/release-tag.sh 1.0.0 --dry-run --allow-branch --force-dirty
```
