# CI Workflow

The repository includes a workflow at `.forgejo/workflows/docker.yml` that validates the Docker image build for `linux/amd64` on pull requests, pushes to `master`, `development`, `release`, `v*` tags, and manual dispatches.

The workflow builds the `api`, `auth-init`, and `web` Dockerfile targets through `docker buildx bake validate-amd64`.

It does not:

- log in to a registry
- push images

It expects a Forgejo runner with:

- the `docker-build` label
- Docker access
- outbound access to the npm and PyPI package registries
