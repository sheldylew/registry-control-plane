variable "REVISION" {
  default = "dev"
}

variable "VERSION" {
  default = "dev"
}

variable "BUILD_TIME" {
  default = ""
}

# Single-platform target used when images need to be loaded into the local
# Docker image store, for example by scripts/docker-save.sh before docker save.
variable "PLATFORM" {
  default = "linux/amd64"
}

# CI and registry publish targets build both supported runtime architectures.
variable "PLATFORMS" {
  default = ["linux/amd64", "linux/arm64"]
}

variable "IMAGE_PREFIX" {
  default = "registry-control-plane"
}

variable "IMAGE_TAG" {
  default = "latest"
}

# Optional second tag for publish targets. Stable release tags use this to also
# move the latest image aliases without affecting validation or local exports.
variable "IMAGE_TAG_ALT" {
  default = ""
}

group "default" {
  targets = ["validate-native"]
}

# Local image export path. This intentionally stays single-platform because
# type=docker loads images into the local Docker image store.
group "local-export" {
  targets = ["api-local", "auth-init-local", "web-local", "nginx-local"]
}

# Pull request path. Builds each runtime image for the runner's native
# architecture without loading local images or pushing to the registry.
group "validate-native" {
  targets = ["api-validate", "auth-init-validate", "web-validate", "nginx-validate"]
}

# Publish path. Each target pushes its own multi-arch image manifest.
group "publish" {
  targets = ["api-publish", "auth-init-publish", "web-publish", "nginx-publish"]
}

# Shared Dockerfile context and OCI metadata for every target.
target "common" {
  context = "."
  dockerfile = "Dockerfile"
  args = {
    APP_VERSION = VERSION
    APP_REVISION = REVISION
    APP_BUILD_TIME = BUILD_TIME
    APP_IMAGE_TAG = IMAGE_TAG
  }
  # Reuse a runner-local BuildKit cache across validation and publish jobs.
  cache-from = ["type=local,src=/tmp/buildkit-registry-control-plane"]
  # Export updated cache contents back to the same path after each build.
  cache-to = ["type=local,dest=/tmp/buildkit-registry-control-plane,mode=max"]
  labels = {
    "org.opencontainers.image.created" = BUILD_TIME
    "org.opencontainers.image.ref.name" = IMAGE_TAG
    "org.opencontainers.image.revision" = REVISION
    "org.opencontainers.image.source" = "https://github.com/sheldylew/registry-control-plane"
    "org.opencontainers.image.version" = VERSION
  }
}

# Shared settings for local image loading.
target "local" {
  inherits = ["common"]
  platforms = ["${PLATFORM}"]
  output = ["type=docker"]
}

# Shared settings for native-arch validation builds.
target "validate" {
  inherits = ["common"]
  platforms = ["${PLATFORM}"]
  output = ["type=cacheonly"]
}

# Shared settings for multi-arch validation builds.
target "multiarch-validate" {
  inherits = ["common"]
  platforms = PLATFORMS
  output = ["type=cacheonly"]
}

# Shared settings for registry publishing.
target "multiarch-publish" {
  inherits = ["common"]
  platforms = PLATFORMS
  output = ["type=registry"]
}

# Service definitions shared by local export, validation, and publish targets.
target "api-base" {
  target = "api"
  tags = ["${IMAGE_PREFIX}-api:${IMAGE_TAG}"]
}

target "auth-init-base" {
  target = "auth-init"
  tags = ["${IMAGE_PREFIX}-auth-init:${IMAGE_TAG}"]
}

target "web-base" {
  target = "web"
  tags = ["${IMAGE_PREFIX}-web:${IMAGE_TAG}"]
}

target "nginx-base" {
  target = "nginx"
  tags = ["${IMAGE_PREFIX}-nginx:${IMAGE_TAG}"]
}

# Local-export targets used by scripts/docker-save.sh.
target "api-local" {
  inherits = ["api-base", "local"]
}

target "auth-init-local" {
  inherits = ["auth-init-base", "local"]
}

target "web-local" {
  inherits = ["web-base", "local"]
}

target "nginx-local" {
  inherits = ["nginx-base", "local"]
}

# Multi-arch validation targets used by pull requests.
target "api-validate" {
  inherits = ["api-base", "validate"]
}

target "auth-init-validate" {
  inherits = ["auth-init-base", "validate"]
}

target "web-validate" {
  inherits = ["web-base", "validate"]
}

target "nginx-validate" {
  inherits = ["nginx-base", "validate"]
}

# Multi-arch publish targets used by push, tag, and manual workflow runs.
target "api-publish" {
  inherits = ["api-base", "multiarch-publish"]
  tags = IMAGE_TAG_ALT == "" ? [
    "${IMAGE_PREFIX}-api:${IMAGE_TAG}",
  ] : [
    "${IMAGE_PREFIX}-api:${IMAGE_TAG}",
    "${IMAGE_PREFIX}-api:${IMAGE_TAG_ALT}",
  ]
}

target "auth-init-publish" {
  inherits = ["auth-init-base", "multiarch-publish"]
  tags = IMAGE_TAG_ALT == "" ? [
    "${IMAGE_PREFIX}-auth-init:${IMAGE_TAG}",
  ] : [
    "${IMAGE_PREFIX}-auth-init:${IMAGE_TAG}",
    "${IMAGE_PREFIX}-auth-init:${IMAGE_TAG_ALT}",
  ]
}

target "web-publish" {
  inherits = ["web-base", "multiarch-publish"]
  tags = IMAGE_TAG_ALT == "" ? [
    "${IMAGE_PREFIX}-web:${IMAGE_TAG}",
  ] : [
    "${IMAGE_PREFIX}-web:${IMAGE_TAG}",
    "${IMAGE_PREFIX}-web:${IMAGE_TAG_ALT}",
  ]
}

target "nginx-publish" {
  inherits = ["nginx-base", "multiarch-publish"]
  tags = IMAGE_TAG_ALT == "" ? [
    "${IMAGE_PREFIX}-nginx:${IMAGE_TAG}",
  ] : [
    "${IMAGE_PREFIX}-nginx:${IMAGE_TAG}",
    "${IMAGE_PREFIX}-nginx:${IMAGE_TAG_ALT}",
  ]
}
