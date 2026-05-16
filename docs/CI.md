# CI Workflow

The repository includes a workflow at `.forgejo/workflows/docker.yml` that validates Docker builds on pull requests and publishes multi-arch images on branch or tag pushes.

Pull requests build the `api`, `auth-init`, `web`, and `nginx` Dockerfile targets through `docker buildx bake --allow=fs=/tmp validate-native` without loading or pushing images. Validation intentionally uses the runner's native platform.

Pushes to `master`, `development`, `release`, `v*` tags, and manual dispatches log in to `registry.sheldylew.com` and publish the same four targets one at a time with `docker buildx bake --allow=fs=/tmp`. Publish jobs install non-native `binfmt` support and push `linux/amd64` plus `linux/arm64` manifests.

Published branch tags are:

- `master`: `edge`
- `development`: `nightly`
- `release`: `release`
- `v*` tags: the Git tag name
- stable SemVer tags such as `v1.2.3`: the Git tag name and `latest`
- other manual refs: the short commit SHA

The workflow publishes these image names:

- `registry.sheldylew.com/sheldylew/registry-control-plane-api:<tag>`
- `registry.sheldylew.com/sheldylew/registry-control-plane-auth-init:<tag>`
- `registry.sheldylew.com/sheldylew/registry-control-plane-web:<tag>`
- `registry.sheldylew.com/sheldylew/registry-control-plane-nginx:<tag>`

It expects a Forgejo runner with:

- the `docker-build` label
- Docker access
- permission to run `tonistiigi/binfmt` with `--privileged` for non-native architecture emulation during publish jobs
- permission to use `/tmp/buildkit-registry-control-plane` as the runner-local BuildKit cache
- outbound access to the npm and PyPI package registries
- `REGISTRY_USERNAME` and `REGISTRY_TOKEN` secrets for publish runs

The workflow reuses a named `forgejo-builder` buildx builder and prunes cache entries older than ten days after each run.
