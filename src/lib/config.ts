import "server-only";

/**
 * Server-side configuration, read from the environment at request time so one
 * built image can run against any environment.
 */

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function apiBaseUrl(): string {
  return trimTrailingSlash(process.env.API_BASE_URL ?? "http://localhost:8000");
}

export function simulatorBaseUrl(): string {
  return trimTrailingSlash(process.env.SIMULATOR_BASE_URL ?? "http://localhost:8100");
}

/** Developer controls drive the carrier simulator; they are off unless asked for. */
export function devToolsEnabled(): boolean {
  return process.env.ENABLE_DEV_TOOLS === "true";
}
