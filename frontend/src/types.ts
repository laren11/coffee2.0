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

export type LanguageOption = {
  id: 'en' | 'sl' | 'hr' | 'de' | 'it'
  label: string
  native_label: string
}

export type VideoOrientation = {
  id: 'portrait' | 'landscape'
  label: string
  aspect_ratio: '9:16' | '16:9'
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
    languages: LanguageOption[]
    videoOrientations: VideoOrientation[]
    ugcCreators: UgcCreator[]
  }
}

export type SubmitGenerationPayload = {
  token: string
  productIds: string[]
  contentType: 'image' | 'video'
  language: LanguageOption['id']
  videoStyle: '' | 'ugc' | 'ad'
  videoOrientation: '' | VideoOrientation['id']
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
  pipeline_stage: 'provider' | 'starter_frame' | 'video_render'
  stage_label: string
  content_type: 'image' | 'video'
  used_reference_images: boolean
  guidance_note: string
}

export type GeneratedAsset = {
  url: string
  file_name?: string
  content_type?: string
}

export type GenerationHistoryItem = {
  id: number
  job_token: string
  provider_request_id: string
  model_id: string
  model_label: string
  pipeline_stage: 'provider' | 'starter_frame' | 'video_render'
  product_id: string
  product_name: string
  product_ids: string[]
  product_names: string[]
  content_type: 'image' | 'video'
  language: LanguageOption['id']
  video_style: '' | 'ugc' | 'ad'
  video_orientation: '' | VideoOrientation['id']
  aspect_ratio: string
  prompt: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  used_reference_images: boolean
  guidance_note: string
  error_message: string
  result_description: string
  assets: GeneratedAsset[]
  created_at: string
  updated_at: string
}

export type GenerationHistoryResponse = {
  items: GenerationHistoryItem[]
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
  model_label?: string
  request_id?: string
  pipeline_stage?: 'provider' | 'starter_frame' | 'video_render'
  stage_label?: string
}

export type AuthResponse = {
  token: string
  user: {
    username: string
  }
}
