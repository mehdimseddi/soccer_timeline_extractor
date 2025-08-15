/* Lightweight logger with levels; no-ops in production for debug/info */
export type LogLevel = "debug" | "info" | "warn" | "error";

const isProd = typeof process !== "undefined" && process.env && process.env.NODE_ENV === "production";

function log(level: LogLevel, ...args: unknown[]): void {
  if ((level === "debug" || level === "info") && isProd) return;
  const fn = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
  fn(...args);
}

export const logger = {
  debug: (...args: unknown[]) => log("debug", ...args),
  info: (...args: unknown[]) => log("info", ...args),
  warn: (...args: unknown[]) => log("warn", ...args),
  error: (...args: unknown[]) => log("error", ...args),
};
