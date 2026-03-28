import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useState,
} from 'react'
import type { ChangeEvent, CSSProperties, FormEvent } from 'react'

import {
  ApiError,
  clearStoredToken,
  fetchCatalog,
  fetchGenerationStatus,
  fetchHistory,
  fetchMe,
  getStoredToken,
  login,
  storeToken,
  submitGeneration,
} from './api'
import './App.css'
import type {
  CatalogResponse,
  GeneratedAsset,
  GenerationHistoryItem,
  GenerationStatusResponse,
  LanguageOption,
  Product,
  UgcCreator,
  VideoOrientation,
  VideoStyle,
} from './types'

type ContentType = 'image' | 'video'
type GenerationPhase =
  | 'idle'
  | 'submitting'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'

type AuthPhase = 'checking' | 'logged_out' | 'logging_in' | 'ready'

type ActiveJob = {
  token: string
  modelLabel: string
  contentType: ContentType
  guidanceNote: string
  usedReferenceImages: boolean
}

const FALLBACK_CATALOG: CatalogResponse = {
  products: [],
  generation_options: {
    imageAspectRatios: ['1:1', '4:5', '16:9', '9:16'],
    videoAspectRatios: ['9:16', '16:9'],
    videoStyles: [
      {
        id: 'ugc',
        label: 'UGC Video',
        description: 'Creator-style, handheld, social-first content.',
      },
      {
        id: 'ad',
        label: 'Ad Video',
        description: 'Polished, commercial-style branded content.',
      },
    ],
    languages: [
      { id: 'en', label: 'English', native_label: 'English' },
      { id: 'sl', label: 'Slovenian', native_label: 'Slovenscina' },
      { id: 'hr', label: 'Croatian', native_label: 'Hrvatski' },
      { id: 'de', label: 'German', native_label: 'Deutsch' },
      { id: 'it', label: 'Italian', native_label: 'Italiano' },
    ],
    videoOrientations: [
      {
        id: 'portrait',
        label: 'Portrait',
        aspect_ratio: '9:16',
        description: 'Best for Reels, TikTok, Stories, and paid social.',
      },
      {
        id: 'landscape',
        label: 'Landscape',
        aspect_ratio: '16:9',
        description: 'Best for widescreen ads, YouTube, and landing pages.',
      },
    ],
    ugcCreators: [],
  },
}

function App() {
  const [authPhase, setAuthPhase] = useState<AuthPhase>('checking')
  const [authToken, setAuthToken] = useState(() => getStoredToken())
  const [currentUsername, setCurrentUsername] = useState('')
  const [loginUsername, setLoginUsername] = useState('coffee')
  const [loginPassword, setLoginPassword] = useState('coffe20')
  const [loginError, setLoginError] = useState('')
  const [sessionError, setSessionError] = useState('')

  const [catalog, setCatalog] = useState<CatalogResponse>(FALLBACK_CATALOG)
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [historyItems, setHistoryItems] = useState<GenerationHistoryItem[]>([])
  const [historyError, setHistoryError] = useState('')
  const [selectedProductId, setSelectedProductId] = useState('')
  const [contentType, setContentType] = useState<ContentType>('image')
  const [selectedLanguage, setSelectedLanguage] = useState<LanguageOption['id']>('en')
  const [videoStyle, setVideoStyle] = useState<'' | 'ugc' | 'ad'>('ugc')
  const [videoOrientation, setVideoOrientation] = useState<'' | VideoOrientation['id']>(
    'portrait',
  )
  const [selectedUgcCreatorId, setSelectedUgcCreatorId] = useState('')
  const [imageAspectRatio, setImageAspectRatio] = useState('1:1')
  const [includeAudio, setIncludeAudio] = useState(true)
  const [prompt, setPrompt] = useState(
    'Create a premium high-converting ad with a strong opening hook, realistic product interaction, persuasive benefit moments, and a clean final CTA-ready ending.',
  )
  const [referenceImages, setReferenceImages] = useState<File[]>([])
  const [phase, setPhase] = useState<GenerationPhase>('idle')
  const [submissionError, setSubmissionError] = useState('')
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null)
  const [statusLogs, setStatusLogs] = useState<string[]>([])
  const [resultDescription, setResultDescription] = useState('')
  const [generatedAssets, setGeneratedAssets] = useState<GeneratedAsset[]>([])

  const deferredPrompt = useDeferredValue(prompt)
  const selectedProduct = catalog.products.find(
    (product) => product.id === selectedProductId,
  )
  const selectedUgcCreator = catalog.generation_options.ugcCreators.find(
    (creator) => creator.id === selectedUgcCreatorId,
  )
  const selectedLanguageOption = catalog.generation_options.languages.find(
    (language) => language.id === selectedLanguage,
  )
  const selectedVideoOrientation = catalog.generation_options.videoOrientations.find(
    (orientation) => orientation.id === videoOrientation,
  )
  const imageAspectRatios = catalog.generation_options.imageAspectRatios
  const videoStyles = catalog.generation_options.videoStyles
  const languageOptions = catalog.generation_options.languages
  const videoOrientations = catalog.generation_options.videoOrientations

  const resetGenerationState = () => {
    setPhase('idle')
    setSubmissionError('')
    setActiveJob(null)
    setStatusLogs([])
    setResultDescription('')
    setGeneratedAssets([])
  }

  const clearSession = useEffectEvent(() => {
    clearStoredToken()
    setAuthToken('')
    setCurrentUsername('')
    setAuthPhase('logged_out')
    setCatalog(FALLBACK_CATALOG)
    setHistoryItems([])
    setHistoryError('')
    setLoadingCatalog(false)
    resetGenerationState()
  })

  const refreshHistory = useEffectEvent(async () => {
    if (!authToken) {
      return
    }

    try {
      const data = await fetchHistory(authToken)
      startTransition(() => {
        setHistoryItems(data.items)
        setHistoryError('')
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession()
        return
      }
      setHistoryError(
        error instanceof Error
          ? error.message
          : 'Unable to load your generation history.',
      )
    }
  })

  useEffect(() => {
    if (!authToken) {
      setAuthPhase('logged_out')
      setLoadingCatalog(false)
      return
    }

    let cancelled = false

    const hydrateSession = async () => {
      setAuthPhase('checking')
      setLoadingCatalog(true)
      setCatalogError('')
      setHistoryError('')

      try {
        const [user, data, history] = await Promise.all([
          fetchMe(authToken),
          fetchCatalog(authToken),
          fetchHistory(authToken),
        ])
        if (cancelled) {
          return
        }

        startTransition(() => {
          setCurrentUsername(user.username)
          setCatalog(data)
          setSelectedProductId((current) => current || data.products[0]?.id || '')
          setSelectedUgcCreatorId(
            (current) => current || data.generation_options.ugcCreators[0]?.id || '',
          )
          setSelectedLanguage(
            (current) => current || data.generation_options.languages[0]?.id || 'en',
          )
          setVideoOrientation(
            (current) =>
              current || data.generation_options.videoOrientations[0]?.id || 'portrait',
          )
          setHistoryItems(history.items)
          setSessionError('')
          setAuthPhase('ready')
        })
      } catch (error) {
        if (cancelled) {
          return
        }
        if (error instanceof ApiError && error.status === 401) {
          clearSession()
          return
        }
        clearStoredToken()
        setAuthToken('')
        setCurrentUsername('')
        setCatalog(FALLBACK_CATALOG)
        setHistoryItems([])
        setCatalogError('')
        setSessionError(
          error instanceof Error
            ? error.message
            : 'Unable to restore your session. Please sign in again.',
        )
        setAuthPhase('logged_out')
      } finally {
        if (!cancelled) {
          setLoadingCatalog(false)
        }
      }
    }

    void hydrateSession()

    return () => {
      cancelled = true
    }
  }, [authToken])

  useEffect(() => {
    if (!selectedProductId && catalog.products[0]) {
      setSelectedProductId(catalog.products[0].id)
    }
  }, [catalog.products, selectedProductId])

  useEffect(() => {
    const creatorIds = catalog.generation_options.ugcCreators.map((creator) => creator.id)
    if (!creatorIds.length) {
      return
    }
    if (!selectedUgcCreatorId || !creatorIds.includes(selectedUgcCreatorId)) {
      setSelectedUgcCreatorId(catalog.generation_options.ugcCreators[0].id)
    }
  }, [catalog.generation_options.ugcCreators, selectedUgcCreatorId])

  useEffect(() => {
    if (!selectedLanguage && catalog.generation_options.languages[0]) {
      setSelectedLanguage(catalog.generation_options.languages[0].id)
    }
  }, [catalog.generation_options.languages, selectedLanguage])

  useEffect(() => {
    if (!videoOrientation && catalog.generation_options.videoOrientations[0]) {
      setVideoOrientation(catalog.generation_options.videoOrientations[0].id)
    }
  }, [catalog.generation_options.videoOrientations, videoOrientation])

  useEffect(() => {
    if (!imageAspectRatios.includes(imageAspectRatio)) {
      setImageAspectRatio(imageAspectRatios[0] || '1:1')
    }
  }, [imageAspectRatio, imageAspectRatios])

  const pollJob = useEffectEvent(async () => {
    if (!activeJob || !authToken) {
      return
    }

    try {
      const status: GenerationStatusResponse = await fetchGenerationStatus(
        authToken,
        activeJob.token,
      )
      const nextLogs =
        status.logs
          ?.map((log) => log.message)
          .filter((message): message is string => Boolean(message))
          .slice(-4) || []
      const shouldRefreshHistory =
        status.state === 'completed' || status.state === 'failed'

      startTransition(() => {
        setStatusLogs(nextLogs)
        setSubmissionError(status.error || '')

        if (status.state === 'queued') {
          setPhase('queued')
          return
        }

        if (status.state === 'processing') {
          setPhase('processing')
          return
        }

        if (status.state === 'failed') {
          setPhase('failed')
          return
        }

        if (status.state === 'completed') {
          setPhase('completed')
          setGeneratedAssets(status.assets || [])
          setResultDescription(status.description || '')
        }
      })
      if (shouldRefreshHistory) {
        void refreshHistory()
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession()
        return
      }
      setPhase('failed')
      setSubmissionError(
        error instanceof Error ? error.message : 'Unable to fetch generation status.',
      )
    }
  })

  useEffect(() => {
    if (!activeJob || phase === 'completed' || phase === 'failed') {
      return
    }

    void pollJob()
    const intervalId = window.setInterval(() => {
      void pollJob()
    }, 5000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [activeJob, phase])

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLoginError('')
    setSessionError('')
    setAuthPhase('logging_in')

    try {
      const response = await login(loginUsername, loginPassword)
      storeToken(response.token)
      setAuthToken(response.token)
      setCurrentUsername(response.user.username)
    } catch (error) {
      setLoginError(
        error instanceof Error ? error.message : 'Unable to sign in right now.',
      )
      setAuthPhase('logged_out')
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!selectedProductId || !authToken) {
      return
    }

    setPhase('submitting')
    setSubmissionError('')
    setGeneratedAssets([])
    setResultDescription('')
    setStatusLogs([])

    try {
      const response = await submitGeneration({
        token: authToken,
        productId: selectedProductId,
        contentType,
        language: selectedLanguage,
        videoStyle: contentType === 'video' ? videoStyle : '',
        videoOrientation: contentType === 'video' ? videoOrientation : '',
        ugcCreatorId:
          contentType === 'video' && videoStyle === 'ugc' ? selectedUgcCreatorId : '',
        prompt,
        aspectRatio:
          contentType === 'video'
            ? selectedVideoOrientation?.aspect_ratio || '9:16'
            : imageAspectRatio,
        includeAudio,
        referenceImages,
      })

      startTransition(() => {
        setActiveJob({
          token: response.job_token,
          modelLabel: response.model_label,
          contentType: response.content_type,
          guidanceNote: response.guidance_note,
          usedReferenceImages: response.used_reference_images,
        })
        setPhase('queued')
      })
      void refreshHistory()
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession()
        return
      }
      setPhase('failed')
      setSubmissionError(
        error instanceof Error ? error.message : 'Unable to submit generation job.',
      )
    }
  }

  const handleReferenceImagesChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []).slice(0, 6)
    setReferenceImages(files)
  }

  const handleLogout = () => {
    clearSession()
  }

  const formatHistoryTimestamp = (value: string) =>
    new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value))

  const promptSummary = deferredPrompt.trim()
    ? deferredPrompt.trim()
    : 'Your creative brief will appear here once you start typing.'

  const isWorking = phase === 'submitting' || phase === 'queued' || phase === 'processing'
  const needsUgcCreator = contentType === 'video' && videoStyle === 'ugc'
  const canSubmit =
    Boolean(selectedProductId && prompt.trim() && selectedLanguage) &&
    (contentType === 'image' || Boolean(videoOrientation)) &&
    (!needsUgcCreator || Boolean(selectedUgcCreatorId)) &&
    !isWorking
  const primaryAsset = generatedAssets[0]
  const productPalette = selectedProduct?.palette || ['#B97A5B', '#F5E6D6', '#6D4A38']
  const previewAspectRatio =
    contentType === 'video'
      ? selectedVideoOrientation?.aspect_ratio || '9:16'
      : imageAspectRatio

  if (authPhase === 'checking') {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="eyebrow">Coffee 2.0 Content Studio</p>
          <h1>Checking your session...</h1>
        </div>
      </div>
    )
  }

  if (authPhase === 'logged_out' || authPhase === 'logging_in') {
    return (
      <div className="auth-shell">
        <form className="auth-card" onSubmit={handleLogin}>
          <p className="eyebrow">Coffee 2.0 Content Studio</p>
          <h1>Sign in before generating.</h1>
          <p className="hero-description">
            The app is protected behind a login so only approved users can access
            generation.
          </p>

          <label className="field-block">
            <span className="field-label">Username</span>
            <input
              className="text-input"
              value={loginUsername}
              onChange={(event) => setLoginUsername(event.target.value)}
            />
          </label>

          <label className="field-block">
            <span className="field-label">Password</span>
            <input
              className="text-input"
              type="password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
            />
          </label>

          <div className="credential-hint">
            <strong>Default test login</strong>
            <small>`coffee` / `coffe20`</small>
          </div>

          {sessionError ? <p className="error-banner">{sessionError}</p> : null}
          {loginError ? <p className="error-banner">{loginError}</p> : null}

          <button className="submit-button auth-button" type="submit">
            {authPhase === 'logging_in' ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <div className="topbar">
        <span className="topbar-user">Signed in as {currentUsername}</span>
        <button type="button" className="logout-button" onClick={handleLogout}>
          Log out
        </button>
      </div>

      <header className="hero-banner">
        <div className="hero-copy">
          <p className="eyebrow">Coffee 2.0 Content Studio</p>
          <h1>Create image ads, UGC, and premium product videos from one workflow.</h1>
          <p className="hero-description">
            Pick a Coffee 2.0 product, choose the ad language, switch between image and
            video, and generate polished creative with product references already wired in.
          </p>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          {productPalette.map((color, index) => (
            <span
              key={color}
              className={`orbit orbit-${index + 1}`}
              style={{ background: color } as CSSProperties}
            />
          ))}
        </div>
      </header>

      <main className="workspace">
        <section className="panel catalog-panel">
          <div className="section-heading">
            <p className="section-kicker">1. Choose product</p>
            <h2>Start from the product you want to promote.</h2>
          </div>

          {loadingCatalog ? <p className="muted">Loading Coffee 2.0 products...</p> : null}
          {catalogError ? <p className="error-banner">{catalogError}</p> : null}

          <div className="product-grid">
            {catalog.products.map((product: Product) => {
              const isSelected = product.id === selectedProductId
              return (
                <button
                  key={product.id}
                  type="button"
                  className={`product-card ${isSelected ? 'selected' : ''}`}
                  style={
                    {
                      '--card-start': product.palette[0],
                      '--card-mid': product.palette[1],
                      '--card-end': product.palette[2],
                    } as CSSProperties
                  }
                  onClick={() => setSelectedProductId(product.id)}
                >
                  <span className="product-name">{product.name}</span>
                  <span className="product-tagline">{product.tagline}</span>
                  <small className="card-meta">
                    {product.local_reference_count} local refs ready
                  </small>
                </button>
              )
            })}
          </div>

          {selectedProduct ? (
            <div className="product-details">
              <p className="product-description">{selectedProduct.description}</p>
              <ul className="benefit-list">
                {selectedProduct.benefits.map((benefit) => (
                  <li key={benefit}>{benefit}</li>
                ))}
              </ul>
              <p className="asset-note">
                Product photo folder: <code>{selectedProduct.asset_folder}</code>
              </p>
              <p className="asset-note">
                Best results usually come from 3 to 6 product photos: front packshot, 45
                degree angle, close label detail, in-hand shot, and one lifestyle scene.
              </p>
            </div>
          ) : null}
        </section>

        <section className="panel studio-panel">
          <div className="section-heading">
            <p className="section-kicker">2. Build the creative brief</p>
            <h2>Choose the language, format, and custom direction.</h2>
          </div>

          <form className="studio-form" onSubmit={handleSubmit}>
            <div className="field-block">
              <label className="field-label">Ad language</label>
              <div className="choice-grid compact-grid">
                {languageOptions.map((language: LanguageOption) => (
                  <button
                    key={language.id}
                    type="button"
                    className={`choice-card ${selectedLanguage === language.id ? 'active' : ''}`}
                    onClick={() => setSelectedLanguage(language.id)}
                  >
                    <span>{language.label}</span>
                    <small>{language.native_label}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className="field-block">
              <label className="field-label">Output type</label>
              <div className="segmented-control">
                {(['image', 'video'] as ContentType[]).map((type) => (
                  <button
                    key={type}
                    type="button"
                    className={contentType === type ? 'active' : ''}
                    onClick={() => setContentType(type)}
                  >
                    {type === 'image' ? 'Image Ad' : 'Video'}
                  </button>
                ))}
              </div>
            </div>

            {contentType === 'video' ? (
              <>
                <div className="field-block">
                  <label className="field-label">Video style</label>
                  <div className="choice-grid">
                    {videoStyles.map((style: VideoStyle) => (
                      <button
                        key={style.id}
                        type="button"
                        className={`choice-card ${videoStyle === style.id ? 'active' : ''}`}
                        onClick={() => setVideoStyle(style.id)}
                      >
                        <span>{style.label}</span>
                        <small>{style.description}</small>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="field-block">
                  <label className="field-label">Video orientation</label>
                  <div className="choice-grid">
                    {videoOrientations.map((orientation: VideoOrientation) => (
                      <button
                        key={orientation.id}
                        type="button"
                        className={`choice-card ${videoOrientation === orientation.id ? 'active' : ''}`}
                        onClick={() => setVideoOrientation(orientation.id)}
                      >
                        <span>{orientation.label}</span>
                        <small>{orientation.description}</small>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            ) : null}

            {needsUgcCreator ? (
              <div className="field-block">
                <label className="field-label">UGC creator preset</label>
                <div className="choice-grid">
                  {catalog.generation_options.ugcCreators.map((creator: UgcCreator) => (
                    <button
                      key={creator.id}
                      type="button"
                      className={`choice-card ${selectedUgcCreatorId === creator.id ? 'active' : ''}`}
                      onClick={() => setSelectedUgcCreatorId(creator.id)}
                    >
                      <span>{creator.name}</span>
                      <small>{creator.description}</small>
                      <small>{creator.local_reference_count} local refs ready</small>
                    </button>
                  ))}
                </div>
                {selectedUgcCreator ? (
                  <>
                    <p className="asset-note">
                      Creator photo folder: <code>{selectedUgcCreator.asset_folder}</code>
                    </p>
                    <p className="asset-note">
                      Upload 4 to 8 rights-cleared creator photos if you want a consistent
                      face. Without them, the preset only controls tone, energy, and
                      delivery.
                    </p>
                  </>
                ) : null}
              </div>
            ) : null}

            {contentType === 'image' ? (
              <div className="field-block">
                <label className="field-label">Image aspect ratio</label>
                <div className="pill-row">
                  {imageAspectRatios.map((ratio) => (
                    <button
                      key={ratio}
                      type="button"
                      className={`pill ${imageAspectRatio === ratio ? 'active' : ''}`}
                      onClick={() => setImageAspectRatio(ratio)}
                    >
                      {ratio}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {contentType === 'video' ? (
              <label className="toggle-card">
                <input
                  type="checkbox"
                  checked={includeAudio}
                  onChange={(event) => setIncludeAudio(event.target.checked)}
                />
                <span>
                  <strong>Generate native video audio</strong>
                  <small>
                    Best for spoken UGC and language testing. For the cleanest final ad
                    voiceovers, you may still want to replace it later with a dedicated
                    voice tool.
                  </small>
                </span>
              </label>
            ) : null}

            <div className="field-block">
              <label className="field-label" htmlFor="prompt">
                Custom prompt
              </label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={7}
                placeholder="Describe the exact concept you want. Mention scene, tone, hook, camera feel, claims to highlight, CTA style, and any non-negotiables."
              />
              <p className="helper-text">
                Your custom prompt is treated as a top-priority instruction in the final
                generation prompt. Mention hook, setting, camera feel, spoken line, CTA,
                and any shots you want to avoid.
              </p>
            </div>

            <div className="field-block">
              <label className="field-label" htmlFor="reference_images">
                Extra manual reference photos
              </label>
              <label className="upload-card" htmlFor="reference_images">
                <input
                  id="reference_images"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={handleReferenceImagesChange}
                />
                <span className="upload-title">Upload up to 6 extra images</span>
                <small>
                  The app also auto-loads local images from the product folder and, for
                  UGC, from the selected creator folder.
                </small>
              </label>

              {referenceImages.length ? (
                <div className="file-list">
                  {referenceImages.map((file) => (
                    <span key={`${file.name}-${file.size}`} className="file-chip">
                      {file.name}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            {submissionError ? <p className="error-banner">{submissionError}</p> : null}

            <button className="submit-button" type="submit" disabled={!canSubmit}>
              {phase === 'submitting'
                ? 'Submitting...'
                : phase === 'queued' || phase === 'processing'
                  ? 'Generation running...'
                  : 'Generate content'}
            </button>
          </form>
        </section>

        <section className="panel insight-panel">
          <div className="section-heading">
            <p className="section-kicker">3. Review result</p>
            <h2>Track the job and preview the generated creative.</h2>
          </div>

          <div className="brief-card">
            <span className="mini-label">Prompt preview</span>
            <p>{promptSummary}</p>
            <div className="brief-meta">
              <span>{selectedLanguageOption?.label || 'English'}</span>
              <span>{contentType === 'video' ? selectedVideoOrientation?.label || 'Portrait' : imageAspectRatio}</span>
              <span>{contentType === 'video' ? videoStyle.toUpperCase() : 'IMAGE'}</span>
            </div>
          </div>

          <div className="status-card">
            <div className="status-header">
              <span className={`status-dot ${phase}`} />
              <div>
                <strong>
                  {phase === 'idle' && 'Ready to generate'}
                  {phase === 'submitting' && 'Sending job to fal.ai'}
                  {phase === 'queued' && 'Job queued'}
                  {phase === 'processing' && 'Generation in progress'}
                  {phase === 'completed' && 'Generation completed'}
                  {phase === 'failed' && 'Generation failed'}
                </strong>
                <small>
                  {activeJob
                    ? `${activeJob.modelLabel} - ${activeJob.usedReferenceImages ? 'with refs' : 'no refs'}`
                    : 'Choose a product and submit your first prompt.'}
                </small>
              </div>
            </div>

            {activeJob ? <p className="muted">{activeJob.guidanceNote}</p> : null}

            {statusLogs.length ? (
              <div className="log-list">
                {statusLogs.map((log) => (
                  <p key={log}>{log}</p>
                ))}
              </div>
            ) : null}
          </div>

          <div className="result-card">
            {primaryAsset ? (
              activeJob?.contentType === 'video' ? (
                <div
                  className="result-stage"
                  data-aspect-ratio={previewAspectRatio}
                >
                  <video controls src={primaryAsset.url} className="result-media" />
                </div>
              ) : (
                <div
                  className="result-stage"
                  data-aspect-ratio={previewAspectRatio}
                >
                  <img
                    src={primaryAsset.url}
                    alt="Generated creative"
                    className="result-media"
                  />
                </div>
              )
            ) : (
              <div
                className={`result-placeholder ${isWorking ? 'is-loading' : ''}`}
                data-aspect-ratio={previewAspectRatio}
              >
                <div>
                  {isWorking ? <span className="loader-orb" aria-hidden="true" /> : null}
                  <span>
                    {isWorking
                      ? 'Generating your creative...'
                      : 'Generated content will appear here'}
                  </span>
                  <small>
                    {isWorking
                      ? 'We are keeping the preview area stable while fal.ai renders the next asset.'
                      : 'The prompt now enforces language, premium pacing, and a stronger ad structure for nicer image and video outputs.'}
                  </small>
                </div>
              </div>
            )}

            {resultDescription ? <p className="result-description">{resultDescription}</p> : null}

            {generatedAssets.length > 1 ? (
              <div className="asset-strip">
                {generatedAssets.map((asset) => (
                  <a key={asset.url} href={asset.url} target="_blank" rel="noreferrer">
                    Open asset
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </main>

      <section className="panel history-panel">
        <div className="section-heading">
          <p className="section-kicker">4. Project history</p>
          <h2>View, reopen, and download past generations.</h2>
        </div>

        {historyError ? <p className="error-banner">{historyError}</p> : null}

        {historyItems.length ? (
          <div className="history-grid">
            {historyItems.map((item) => {
              const previewAsset = item.assets[0]
              return (
                <article key={item.id} className="history-card">
                  <div className="history-meta">
                    <strong>{item.product_name}</strong>
                    <small>{formatHistoryTimestamp(item.created_at)}</small>
                  </div>
                  <div className="brief-meta">
                    <span>{item.content_type.toUpperCase()}</span>
                    <span>{item.language.toUpperCase()}</span>
                    <span>{item.status.toUpperCase()}</span>
                  </div>

                  {previewAsset ? (
                    item.content_type === 'video' ? (
                      <div
                        className="history-preview"
                        data-aspect-ratio={item.aspect_ratio || '9:16'}
                      >
                        <video
                          className="history-media"
                          src={previewAsset.url}
                          controls
                          preload="metadata"
                        />
                      </div>
                    ) : (
                      <div
                        className="history-preview"
                        data-aspect-ratio={item.aspect_ratio || '1:1'}
                      >
                        <img
                          className="history-media"
                          src={previewAsset.url}
                          alt={`${item.product_name} history preview`}
                        />
                      </div>
                    )
                  ) : (
                    <div
                      className="history-preview history-empty"
                      data-aspect-ratio={item.aspect_ratio || '1:1'}
                    >
                      <small>
                        {item.status === 'failed'
                          ? item.error_message || 'Generation failed.'
                          : 'Result preview will appear here once the job finishes.'}
                      </small>
                    </div>
                  )}

                  <p className="history-prompt">{item.prompt}</p>
                  <div className="history-actions">
                    {previewAsset ? (
                      <>
                        <a href={previewAsset.url} target="_blank" rel="noreferrer">
                          View
                        </a>
                        <a href={previewAsset.url} download>
                          Download
                        </a>
                      </>
                    ) : (
                      <span className="muted">No asset yet</span>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <div className="history-empty-state">
            <span>No projects yet</span>
            <small>
              Your finished image and video generations will show up here with direct
              view and download links.
            </small>
          </div>
        )}
      </section>
    </div>
  )
}

export default App
