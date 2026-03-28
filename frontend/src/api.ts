import type {
  AuthResponse,
  CatalogResponse,
  GenerationHistoryResponse,
  GenerationStatusResponse,
  SubmitGenerationPayload,
  SubmitGenerationResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
export const AUTH_STORAGE_KEY = 'coffee20_auth_token'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function normalizeTextPreview(value: string) {
  return value.replace(/\s+/g, ' ').trim().slice(0, 240)
}

async function requestWithDiagnostics(
  input: RequestInfo | URL,
  init: RequestInit,
): Promise<Response> {
  const endpoint = typeof input === 'string' ? input : input.toString()

  try {
    return await fetch(input, init)
  } catch (error) {
    const details = [
      'The request failed before the server returned a response.',
      `Endpoint: ${endpoint}`,
    ]

    if (error instanceof Error && error.message) {
      details.push(`Browser error: ${error.message}`)
    }

    details.push(
      'Likely causes: Render cold start timeout, backend crash, CORS misconfiguration, or a temporary network drop.',
    )
    details.push('Open the Render API logs and retry once to capture the matching server-side error.')

    throw new ApiError(details.join('\n'), 0)
  }
}

async function parseResponse<T>(response: Response, endpoint: string): Promise<T> {
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    if (typeof data === 'string') {
      const details = [
        `Request failed with status ${response.status}.`,
        `Endpoint: ${endpoint}`,
      ]
      if (contentType.includes('text/html')) {
        details.push(
          'The API returned HTML instead of JSON, which usually means the backend crashed or Render served an error page.',
        )
      }
      const preview = normalizeTextPreview(data)
      if (preview) {
        details.push(`Response preview: ${preview}`)
      }
      throw new ApiError(details.join('\n'), response.status)
    }

    const detail =
      (data as { detail?: string }).detail ||
      `Request failed with status ${response.status} at ${endpoint}.`
    throw new ApiError(detail, response.status)
  }

  return data as T
}

function buildAuthHeaders(token: string) {
  return {
    Authorization: `Token ${token}`,
  }
}

function ensureUserPayload(
  payload: unknown,
  fallbackMessage: string,
): AuthResponse {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'token' in payload &&
    typeof payload.token === 'string' &&
    'user' in payload &&
    typeof payload.user === 'object' &&
    payload.user !== null &&
    'username' in payload.user &&
    typeof payload.user.username === 'string'
  ) {
    return payload as AuthResponse
  }

  throw new ApiError(fallbackMessage, 500)
}

function ensureMePayload(
  payload: unknown,
  fallbackMessage: string,
): AuthResponse['user'] {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'user' in payload &&
    typeof payload.user === 'object' &&
    payload.user !== null &&
    'username' in payload.user &&
    typeof payload.user.username === 'string'
  ) {
    return (payload as { user: AuthResponse['user'] }).user
  }

  throw new ApiError(fallbackMessage, 500)
}

function ensureCatalogPayload(
  payload: unknown,
  fallbackMessage: string,
): CatalogResponse {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'products' in payload &&
    Array.isArray(payload.products) &&
    'generation_options' in payload &&
    typeof payload.generation_options === 'object' &&
    payload.generation_options !== null
  ) {
    return payload as CatalogResponse
  }

  throw new ApiError(fallbackMessage, 500)
}

function ensureHistoryPayload(
  payload: unknown,
  fallbackMessage: string,
): GenerationHistoryResponse {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'items' in payload &&
    Array.isArray(payload.items)
  ) {
    return payload as GenerationHistoryResponse
  }

  throw new ApiError(fallbackMessage, 500)
}

export function getStoredToken() {
  return window.localStorage.getItem(AUTH_STORAGE_KEY) || ''
}

export function storeToken(token: string) {
  window.localStorage.setItem(AUTH_STORAGE_KEY, token)
}

export function clearStoredToken() {
  window.localStorage.removeItem(AUTH_STORAGE_KEY)
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  const endpoint = `${API_BASE}/auth/login/`
  const response = await requestWithDiagnostics(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  })
  const data = await parseResponse<unknown>(response, endpoint)
  return ensureUserPayload(
    data,
    'The login endpoint returned an unexpected response. Check VITE_API_BASE_URL on the frontend and redeploy it.',
  )
}

export async function fetchMe(token: string): Promise<AuthResponse['user']> {
  const endpoint = `${API_BASE}/auth/me/`
  const response = await requestWithDiagnostics(endpoint, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<unknown>(response, endpoint)
  return ensureMePayload(
    data,
    'The auth session endpoint returned an unexpected response. Check VITE_API_BASE_URL on the frontend and redeploy it.',
  )
}

export async function fetchCatalog(token: string): Promise<CatalogResponse> {
  const endpoint = `${API_BASE}/products/`
  const response = await requestWithDiagnostics(endpoint, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<unknown>(response, endpoint)
  return ensureCatalogPayload(
    data,
    'The catalog endpoint returned an unexpected response. Check VITE_API_BASE_URL on the frontend and redeploy it.',
  )
}

export async function fetchHistory(token: string): Promise<GenerationHistoryResponse> {
  const endpoint = `${API_BASE}/history/`
  const response = await requestWithDiagnostics(endpoint, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<unknown>(response, endpoint)
  return ensureHistoryPayload(
    data,
    'The history endpoint returned an unexpected response. Check VITE_API_BASE_URL on the frontend and redeploy it.',
  )
}

export async function submitGeneration(
  payload: SubmitGenerationPayload,
): Promise<SubmitGenerationResponse> {
  const formData = new FormData()
  payload.productIds.forEach((productId) => {
    formData.append('product_ids', productId)
  })
  formData.append('content_type', payload.contentType)
  formData.append('language', payload.language)
  formData.append('video_style', payload.videoStyle)
  formData.append('video_orientation', payload.videoOrientation)
  formData.append('ugc_creator_id', payload.ugcCreatorId)
  formData.append('prompt', payload.prompt)
  formData.append('aspect_ratio', payload.aspectRatio)
  formData.append('include_audio', String(payload.includeAudio))

  payload.referenceImages.forEach((file) => {
    formData.append('reference_images', file)
  })

  const endpoint = `${API_BASE}/generate/`
  const response = await requestWithDiagnostics(endpoint, {
    method: 'POST',
    headers: buildAuthHeaders(payload.token),
    body: formData,
  })

  return parseResponse<SubmitGenerationResponse>(response, endpoint)
}

export async function fetchGenerationStatus(
  authToken: string,
  jobToken: string,
): Promise<GenerationStatusResponse> {
  const params = new URLSearchParams({ token: jobToken })
  const endpoint = `${API_BASE}/generate/status/?${params.toString()}`
  const response = await requestWithDiagnostics(endpoint, {
    headers: buildAuthHeaders(authToken),
  })
  return parseResponse<GenerationStatusResponse>(response, endpoint)
}
