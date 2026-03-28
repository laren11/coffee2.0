import type {
  AuthResponse,
  CatalogResponse,
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

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const detail =
      typeof data === 'string'
        ? data
        : (data as { detail?: string }).detail || 'Something went wrong.'
    throw new ApiError(detail, response.status)
  }

  return data as T
}

function buildAuthHeaders(token: string) {
  return {
    Authorization: `Token ${token}`,
  }
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
  const response = await fetch(`${API_BASE}/auth/login/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  })
  return parseResponse<AuthResponse>(response)
}

export async function fetchMe(token: string): Promise<AuthResponse['user']> {
  const response = await fetch(`${API_BASE}/auth/me/`, {
    headers: buildAuthHeaders(token),
  })
  const data = await parseResponse<{ user: AuthResponse['user'] }>(response)
  return data.user
}

export async function fetchCatalog(token: string): Promise<CatalogResponse> {
  const response = await fetch(`${API_BASE}/products/`, {
    headers: buildAuthHeaders(token),
  })
  return parseResponse<CatalogResponse>(response)
}

export async function submitGeneration(
  payload: SubmitGenerationPayload,
): Promise<SubmitGenerationResponse> {
  const formData = new FormData()
  formData.append('product_id', payload.productId)
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

  const response = await fetch(`${API_BASE}/generate/`, {
    method: 'POST',
    headers: buildAuthHeaders(payload.token),
    body: formData,
  })

  return parseResponse<SubmitGenerationResponse>(response)
}

export async function fetchGenerationStatus(
  authToken: string,
  jobToken: string,
): Promise<GenerationStatusResponse> {
  const params = new URLSearchParams({ token: jobToken })
  const response = await fetch(`${API_BASE}/generate/status/?${params.toString()}`, {
    headers: buildAuthHeaders(authToken),
  })
  return parseResponse<GenerationStatusResponse>(response)
}
