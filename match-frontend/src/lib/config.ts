// Centralized configuration for environment-aware settings
export const API_BASE_URL: string =
  (typeof import.meta !== "undefined" && (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL) ||
  "http://localhost:8000"; // set VITE_API_BASE_URL in .env for production

export const REQUEST_TIMEOUT_MS: number = 3000000; // 5min default

// Optional API prefix for versioning, e.g., "/api/v1". Defaults to empty string.
export const API_PREFIX: string =
  (typeof import.meta !== "undefined" && (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_PREFIX) ||
  "";
