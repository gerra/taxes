// Thin fetch wrapper: JSON in/out, errors thrown with the server's message.

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    let message = `HTTP ${status}`
    if (typeof body === 'object' && body !== null && 'error' in body) {
      const err = (body as { error: unknown }).error
      if (typeof err === 'string') message = err
      else if (err && typeof err === 'object' && 'message' in err)
        message = String((err as { message: unknown }).message)
      else message = JSON.stringify(err)
    }
    super(message)
    this.status = status
    this.body = body
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const resp = await fetch(url, init)
  const data = resp.status === 204 ? null : await resp.json().catch(() => null)
  if (!resp.ok) throw new ApiError(resp.status, data)
  return data as T
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body),
  put: <T>(url: string, body?: unknown) => request<T>('PUT', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
}
