import { API_BASE_URL, API_PREFIX, REQUEST_TIMEOUT_MS } from "@/lib/config";
import { logger } from "@/lib/logger";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface HttpOptions {
  path: string;
  method?: HttpMethod;
  headers?: Record<string, string>;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  asFormData?: boolean;
}

export class HttpError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly data?: unknown;

  constructor(message: string, status: number, statusText: string, data?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.statusText = statusText;
    this.data = data;
  }
}

export async function http<T = unknown>({
  path,
  method = "GET",
  headers,
  body,
  signal,
  timeoutMs = REQUEST_TIMEOUT_MS,
  asFormData,
}: HttpOptions): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const mergedSignal = mergeSignals(signal, controller.signal);

  try {
    const normalizedPrefix = API_PREFIX ? (API_PREFIX.startsWith("/") ? API_PREFIX : `/${API_PREFIX}`) : "";
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const url = path.startsWith("http") ? path : `${API_BASE_URL}${normalizedPrefix}${normalizedPath}`;
    const init: RequestInit = { method, headers: { ...(headers || {}) }, signal: mergedSignal };

    if (body instanceof FormData || asFormData) {
      init.body = body as BodyInit;
      // Let the browser set Content-Type with boundary
    } else if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { "Content-Type": "application/json", ...init.headers };
    }

    const response = await fetch(url, init);

    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    let data: unknown = undefined;
    try {
      data = isJson ? await response.json() : await response.text();
    } catch {
      // ignore parse error; keep data undefined
    }

    if (!response.ok) {
      const message = (isJson && data && typeof data === "object" && (data as Record<string, unknown>).detail) || response.statusText || "Request failed";
      throw new HttpError(String(message), response.status, response.statusText, data);
    }

    return data as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      logger.warn("HTTP request aborted", { path, method });
      throw new Error("Request was aborted");
    }
    if (err instanceof HttpError) {
      logger.error("HTTP error", { path, method, status: err.status, data: err.data });
      throw err;
    }
    logger.error("Network or unknown error", { path, method, error: err });
    throw new Error("Network error. Please check your connection.");
  } finally {
    clearTimeout(timeout);
  }
}

function mergeSignals(a?: AbortSignal, b?: AbortSignal): AbortSignal | undefined {
  if (!a) return b;
  if (!b) return a;
  const controller = new AbortController();
  const onAbort = (source: AbortSignal) => () => controller.abort(source.reason);
  if (a.aborted) controller.abort(a.reason);
  if (b.aborted) controller.abort(b.reason);
  a.addEventListener("abort", onAbort(a));
  b.addEventListener("abort", onAbort(b));
  return controller.signal;
}
