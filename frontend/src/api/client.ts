export class ApiError extends Error {
  status: number
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

/**
 * `detail` is bij Financiën een string, bij Weekmenu een {code, message}-object,
 * en bij FastAPI-validatiefouten (422) een array — die laatste valt terug op
 * statusText. Het string-pad is ongewijzigd t.o.v. vóór Weekmenu.
 */
async function toApiError(response: Response): Promise<ApiError> {
  let message = response.statusText
  let code: string | undefined
  try {
    const body = (await response.json()) as { detail?: unknown }
    const detail = body.detail
    if (typeof detail === 'string' && detail) {
      message = detail
    } else if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const obj = detail as { code?: unknown; message?: unknown }
      if (typeof obj.message === 'string' && obj.message) message = obj.message
      if (typeof obj.code === 'string') code = obj.code
    }
  } catch {
    // geen JSON-body, statusText volstaat
  }
  return new ApiError(response.status, message, code)
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) throw await toApiError(response)
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
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}

export interface User {
  id: number
  name: string
  email: string
}
