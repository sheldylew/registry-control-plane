import { readFile } from "node:fs/promises";

function parseBuildInfoEnv(content) {
  const values = {};
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }
    const [key, ...valueParts] = trimmed.split("=");
    values[key.trim()] = valueParts.join("=").trim();
  }
  return values;
}

async function readBuildInfoFile(path) {
  try {
    return parseBuildInfoEnv(await readFile(path, "utf8"));
  } catch {
    return {};
  }
}

export async function readWebBuildInfo() {
  const buildInfo = await readBuildInfoFile(process.env.APP_BUILD_INFO_PATH || "/web/build-info.env");
  return {
    version: buildInfo.APP_VERSION || process.env.APP_VERSION || "dev",
    revision: buildInfo.APP_REVISION || process.env.APP_REVISION || process.env.REVISION || "dev",
    built_at: buildInfo.APP_BUILD_TIME || process.env.APP_BUILD_TIME || null,
    image_tag: buildInfo.APP_IMAGE_TAG || process.env.APP_IMAGE_TAG || null,
  };
}
