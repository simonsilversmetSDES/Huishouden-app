export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // geen JSON-body, statusText volstaat
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * Zoals `api`, maar voor multipart-upload: géén Content-Type meegeven zodat de
 * browser zelf de multipart-boundary zet (nodig voor bestand-upload naar
 * /api/imports/preview).
 */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    body: formData,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // geen JSON-body, statusText volstaat
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export interface User {
  id: number
  name: string
  email: string
}
