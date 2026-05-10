# CI Workflow

The repository includes a workflow at `.forgejo/workflows/docker.yml` that validates or publishes the Docker image build for `linux/amd64` and `linux/arm64`.

Pull requests build the `api`, `auth-init`, `web`, and `nginx` Dockerfile targets through `docker buildx bake validate-multiarch` without pushing images.

Pushes to `master`, `development`, `release`, `v*` tags, and manual dispatches log in to `registry.sheldylew.com` and publish the same four targets through `docker buildx bake publish`.

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
- permission to run `tonistiigi/binfmt` with `--privileged` for arm64 emulation
- outbound access to the npm and PyPI package registries
- `REGISTRY_USERNAME` and `REGISTRY_TOKEN` secrets for publish runs
