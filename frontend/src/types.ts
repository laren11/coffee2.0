export type Product = {
  id: string
  name: string
  tagline: string
  description: string
  benefits: string[]
  creative_angles: string[]
  palette: string[]
  base_prompt: string
  asset_folder: string
  local_reference_count: number
}

export type VideoStyle = {
  id: 'ugc' | 'ad'
  label: string
  description: string
}

export type UgcCreator = {
  id: string
  name: string
  description: string
  persona_prompt: string
  asset_folder: string
  local_reference_count: number
}

export type CatalogResponse = {
  products: Product[]
  generation_options: {
    imageAspectRatios: string[]
    videoAspectRatios: string[]
    videoStyles: VideoStyle[]
    ugcCreators: UgcCreator[]
  }
}

export type SubmitGenerationPayload = {
  token: string
  productId: string
  contentType: 'image' | 'video'
  videoStyle: '' | 'ugc' | 'ad'
  ugcCreatorId: string
  prompt: string
  aspectRatio: string
  includeAudio: boolean
  referenceImages: File[]
}

export type SubmitGenerationResponse = {
  job_token: string
  request_id: string
  model_id: string
  model_label: string
  content_type: 'image' | 'video'
  used_reference_images: boolean
  guidance_note: string
}

export type GeneratedAsset = {
  url: string
  file_name?: string
  content_type?: string
}

export type GenerationStatusResponse = {
  state: 'queued' | 'processing' | 'completed' | 'failed'
  queue_position?: number
  logs?: Array<{ message?: string; timestamp?: string | null }>
  assets?: GeneratedAsset[]
  content_type?: 'image' | 'video'
  description?: string
  error?: string
  model_id?: string
  request_id?: string
}

export type AuthResponse = {
  token: string
  user: {
    username: string
  }
}
