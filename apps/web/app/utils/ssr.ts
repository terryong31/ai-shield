/** The longest time a server render waits for the gateway (specs 0044, 0049). */
export const SSR_TIMEOUT_MS = 800

/** Nitro's internal fetch ignores abort signals, so the wait itself has the limit. */
export async function withSsrTimeout<T>(request: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const limit = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`No answer in ${SSR_TIMEOUT_MS} ms`)), SSR_TIMEOUT_MS)
  })
  try {
    return await Promise.race([request, limit])
  } finally {
    clearTimeout(timer)
  }
}
