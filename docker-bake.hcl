variable "REVISION" {
  default = "dev"
}

variable "VERSION" {
  default = "dev"
}

variable "PLATFORM" {
  default = "linux/amd64"
}

variable "IMAGE_PREFIX" {
  default = "registry-control-plane"
}

variable "IMAGE_TAG" {
  default = "latest"
}

group "default" {
  targets = ["validate-amd64"]
}

group "validate-amd64" {
  targets = ["api", "auth-init", "web", "nginx"]
}

target "common" {
  context = "."
  dockerfile = "Dockerfile"
  platforms = ["${PLATFORM}"]
  labels = {
    "org.opencontainers.image.revision" = REVISION
    "org.opencontainers.image.version" = VERSION
  }
  output = ["type=docker"]
}

target "api" {
  inherits = ["common"]
  target = "api"
  tags = ["${IMAGE_PREFIX}-api:${IMAGE_TAG}"]
}

target "auth-init" {
  inherits = ["common"]
  target = "auth-init"
  tags = ["${IMAGE_PREFIX}-auth-init:${IMAGE_TAG}"]
}

target "web" {
  inherits = ["common"]
  target = "web"
  tags = ["${IMAGE_PREFIX}-web:${IMAGE_TAG}"]
}

target "nginx" {
  inherits = ["common"]
  target = "nginx"
  tags = ["${IMAGE_PREFIX}-nginx:${IMAGE_TAG}"]
}
