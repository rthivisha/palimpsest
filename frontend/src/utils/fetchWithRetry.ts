/**
 * fetchWithInitialRetry:
 * Performs an HTTP request with at most ONE retry if and only if the network connection
 * fails before any response is received (e.g. transient ECONNREFUSED or TypeError).
 *
 * Invariants:
 * 1. Retries at most once, and only when the initial connection fails before any response headers/body.
 * 2. If the retry also fails with a network exception, throws the error.
 * 3. Never retries once an HTTP Response object is returned (stream errors are not retried).
 * 4. Never retries when the request was aborted by the client (AbortError).
 */
export async function fetchWithInitialRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  retryDelayMs: number = 500,
  fetchFn: typeof fetch = fetch
): Promise<Response> {
  try {
    return await fetchFn(input, init);
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw err;
    }
    if (retryDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
    }
    if (init?.signal?.aborted) {
      throw err;
    }
    // Single retry attempt before any response
    return await fetchFn(input, init);
  }
}
