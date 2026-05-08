variable "REVISION" {
  default = "dev"
}

variable "VERSION" {
  default = "dev"
}

group "default" {
  targets = ["validate-amd64"]
}

group "validate-amd64" {
  targets = ["api", "auth-init", "web"]
}

target "common" {
  context = "."
  dockerfile = "Dockerfile"
  platforms = ["linux/amd64"]
  labels = {
    "org.opencontainers.image.revision" = REVISION
    "org.opencontainers.image.version" = VERSION
  }
  output = ["type=docker"]
}

target "api" {
  inherits = ["common"]
  target = "api"
  tags = ["registry-control-plane-api:ci"]
}

target "auth-init" {
  inherits = ["common"]
  target = "auth-init"
  tags = ["registry-control-plane-auth-init:ci"]
}

target "web" {
  inherits = ["common"]
  target = "web"
  tags = ["registry-control-plane-web:ci"]
}
