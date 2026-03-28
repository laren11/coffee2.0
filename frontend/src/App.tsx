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

type PromptRecipe = {
  label: string
  text: string
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

function buildPromptRecipes(
  products: Product[],
  contentType: ContentType,
  videoStyle: '' | 'ugc' | 'ad',
  languageLabel: string,
): PromptRecipe[] {
  const productName =
    products.length > 0
      ? products.map((product) => product.name).join(' + ')
      : 'Coffee 2.0'
  const firstBenefit =
    products.flatMap((product) => product.benefits)[0] || 'clear premium product benefits'

  if (contentType === 'image') {
    return [
      {
        label: 'Hero still',
        text: `Create a premium ${languageLabel} image ad for ${productName} with editorial lighting, tactile packaging detail, one bold benefit focus on ${firstBenefit}, and a clean luxury wellness finish.`,
      },
      {
        label: 'Lifestyle still',
        text: `Create a realistic lifestyle image for ${productName} in a believable wellness setting with premium natural light, in-hand product interaction, and a subtle high-converting CTA mood in ${languageLabel}.`,
      },
      {
        label: 'Launch poster',
        text: `Create a launch-day key visual for ${productName} that feels photographed, premium, modern, and social-first, with bold composition, rich texture, and one unforgettable product hero angle in ${languageLabel}.`,
      },
    ]
  }

  if (videoStyle === 'ugc') {
    return [
      {
        label: 'Fast testimonial',
        text: `Create a ${languageLabel} UGC testimonial for ${productName} with a sharp 2-second hook, founder energy, direct eye contact, believable speech, one practical proof moment, and a confident social-native finish.`,
      },
      {
        label: 'Routine reveal',
        text: `Create a ${languageLabel} UGC routine video for ${productName} showing how it fits into a real morning or performance routine, with natural product handling, conversational delivery, and one strong why-this-works line.`,
      },
      {
        label: 'Objection breaker',
        text: `Create a ${languageLabel} UGC ad for ${productName} that starts with a skeptical hook, breaks one common objection, shows the product naturally, and ends with a persuasive recommendation that feels authentic.`,
      },
    ]
  }

  return [
    {
      label: 'Cinematic hook',
      text: `Create a premium ${languageLabel} cinematic ad for ${productName} with an in-scene opening hook, elegant camera movement, persuasive product proof, beautiful lighting, and a clean final hero moment.`,
    },
    {
      label: 'Performance film',
      text: `Create a realistic ${languageLabel} commercial for ${productName} with cinematic motion, tactile closeups, aspirational lifestyle cutaways, product credibility, and a premium direct-response ending.`,
    },
    {
      label: 'Luxury social spot',
      text: `Create a luxury-feeling ${languageLabel} paid social ad for ${productName} with premium pacing, polished movement, believable environments, and a memorable final frame designed to convert.`,
    },
  ]
}

function calculateCreativeStreak(items: GenerationHistoryItem[]) {
  const completedDates = Array.from(
    new Set(
      items
        .filter((item) => item.status === 'completed')
        .map((item) => new Date(item.created_at).toISOString().slice(0, 10)),
    ),
  ).sort()

  if (!completedDates.length) {
    return 0
  }

  let streak = 1
  let cursor = new Date(`${completedDates[completedDates.length - 1]}T00:00:00`)

  for (let index = completedDates.length - 2; index >= 0; index -= 1) {
    const previous = new Date(`${completedDates[index]}T00:00:00`)
    const diffDays = Math.round(
      (cursor.getTime() - previous.getTime()) / (1000 * 60 * 60 * 24),
    )

    if (diffDays !== 1) {
      break
    }

    streak += 1
    cursor = previous
  }

  return streak
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
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([])
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
  const [surpriseHint, setSurpriseHint] = useState('')
  const [brewModeEnabled, setBrewModeEnabled] = useState(false)
  const [brewToastVisible, setBrewToastVisible] = useState(false)
  const [showCompletionBurst, setShowCompletionBurst] = useState(false)

  const deferredPrompt = useDeferredValue(prompt)
  const selectedProducts = catalog.products.filter((product) =>
    selectedProductIds.includes(product.id),
  )
  const primarySelectedProduct = selectedProducts[0]
  const selectedProductNames = selectedProducts.map((product) => product.name)
  const selectedProductFolders = selectedProducts.map((product) => product.asset_folder)
  const selectedProductBenefits = Array.from(
    new Set(selectedProducts.flatMap((product) => product.benefits)),
  )
  const totalSelectedProductRefs = selectedProducts.reduce(
    (sum, product) => sum + product.local_reference_count,
    0,
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
  const promptRecipes = buildPromptRecipes(
    selectedProducts,
    contentType,
    videoStyle,
    selectedLanguageOption?.label || 'English',
  )
  const completedHistoryItems = historyItems.filter((item) => item.status === 'completed')
  const completedCount = completedHistoryItems.length
  const ugcWins = completedHistoryItems.filter((item) => item.video_style === 'ugc').length
  const cinemaWins = completedHistoryItems.filter((item) => item.video_style === 'ad').length
  const languageCount = new Set(completedHistoryItems.map((item) => item.language)).size
  const creativeStreak = calculateCreativeStreak(historyItems)
  const creativeScore =
    completedCount * 40 +
    ugcWins * 18 +
    cinemaWins * 22 +
    languageCount * 15 +
    creativeStreak * 28
  const achievementChips = [
    {
      label: 'First Brew',
      unlocked: completedCount >= 1,
      hint: 'Finish your first generation',
    },
    {
      label: 'Triple Shot',
      unlocked: completedCount >= 3,
      hint: 'Ship three completed creatives',
    },
    {
      label: 'UGC Machine',
      unlocked: ugcWins >= 2,
      hint: 'Complete two UGC videos',
    },
    {
      label: 'Cinema Club',
      unlocked: cinemaWins >= 2,
      hint: 'Complete two ad videos',
    },
    {
      label: 'Polyglot',
      unlocked: languageCount >= 3,
      hint: 'Generate in three languages',
    },
  ]

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
    setSurpriseHint('')
    setBrewToastVisible(false)
    setShowCompletionBurst(false)
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
          setSelectedProductIds((current) => {
            const validCurrent = current.filter((productId) =>
              data.products.some((product) => product.id === productId),
            )
            if (validCurrent.length) {
              return validCurrent
            }
            return data.products[0] ? [data.products[0].id] : []
          })
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
    const validSelectedIds = selectedProductIds.filter((productId) =>
      catalog.products.some((product) => product.id === productId),
    )
    if (validSelectedIds.length !== selectedProductIds.length) {
      setSelectedProductIds(validSelectedIds)
      return
    }
    if (!validSelectedIds.length && catalog.products[0]) {
      setSelectedProductIds([catalog.products[0].id])
    }
  }, [catalog.products, selectedProductIds])

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

  useEffect(() => {
    if (contentType === 'video' && videoStyle === 'ugc' && !includeAudio) {
      setIncludeAudio(true)
    }
  }, [contentType, includeAudio, videoStyle])

  useEffect(() => {
    let sequence = ''

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
        return
      }

      sequence = `${sequence}${event.key.toLowerCase()}`.slice(-4)
      if (sequence === 'brew') {
        setBrewModeEnabled((current) => !current)
        setBrewToastVisible(true)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

  useEffect(() => {
    if (!brewToastVisible) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      setBrewToastVisible(false)
    }, 2200)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [brewToastVisible])

  useEffect(() => {
    if (!showCompletionBurst) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      setShowCompletionBurst(false)
    }, 1800)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [showCompletionBurst])

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
          setShowCompletionBurst(true)
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

    if (!selectedProductIds.length || !authToken) {
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
        productIds: selectedProductIds,
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
        includeAudio: contentType === 'video' && videoStyle === 'ugc' ? true : includeAudio,
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

  const toggleProductSelection = (productId: string) => {
    setSelectedProductIds((current) =>
      current.includes(productId)
        ? current.filter((id) => id !== productId)
        : [...current, productId],
    )
  }

  const selectAllProducts = () => {
    setSelectedProductIds(catalog.products.map((product) => product.id))
  }

  const clearProductSelection = () => {
    setSelectedProductIds([])
  }

  const handleReferenceImagesChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []).slice(0, 6)
    setReferenceImages(files)
  }

  const handleLogout = () => {
    clearSession()
  }

  const handleSurprisePrompt = () => {
    const recipe = promptRecipes[Math.floor(Math.random() * promptRecipes.length)]
    setPrompt(recipe.text)
    setSurpriseHint(`Loaded "${recipe.label}"`)
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
  const isUgcAudioLocked = contentType === 'video' && videoStyle === 'ugc'
  const canSubmit =
    Boolean(selectedProductIds.length && prompt.trim() && selectedLanguage) &&
    (contentType === 'image' || Boolean(videoOrientation)) &&
    (!needsUgcCreator || Boolean(selectedUgcCreatorId)) &&
    !isWorking
  const primaryAsset = generatedAssets[0]
  const productPalette =
    Array.from(new Set(selectedProducts.flatMap((product) => product.palette))).slice(0, 3)
      .concat(['#B97A5B', '#F5E6D6', '#6D4A38'])
      .slice(0, 3)
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
    <div className={`app-shell ${brewModeEnabled ? 'brew-mode' : ''}`}>
      {brewToastVisible ? (
        <div className="brew-toast">Midnight Roast Mode unlocked</div>
      ) : null}

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
            Pick one Coffee 2.0 product or build a product lineup, choose the ad language,
            switch between image and video, and generate polished creative with product
            references already wired in.
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

      <section className="scoreboard-strip">
        <article className="score-card">
          <span className="mini-label">Creative Score</span>
          <strong>{creativeScore}</strong>
          <small>Built from completions, formats, languages, and streaks.</small>
        </article>
        <article className="score-card">
          <span className="mini-label">Current Streak</span>
          <strong>{creativeStreak} day{creativeStreak === 1 ? '' : 's'}</strong>
          <small>Consecutive active creation days based on completed projects.</small>
        </article>
        <article className="score-card">
          <span className="mini-label">Completed Shots</span>
          <strong>{completedCount}</strong>
          <small>{ugcWins} UGC wins, {cinemaWins} cinematic wins.</small>
        </article>
        <article className="score-card achievement-card">
          <span className="mini-label">Achievements</span>
          <div className="achievement-strip">
            {achievementChips.map((chip) => (
              <span
                key={chip.label}
                className={`achievement-chip ${chip.unlocked ? 'unlocked' : ''}`}
                title={chip.hint}
              >
                {chip.label}
              </span>
            ))}
          </div>
        </article>
      </section>

      <main className="workspace">
        <section className="panel catalog-panel">
          <div className="section-heading">
            <p className="section-kicker">1. Choose products</p>
            <h2>Pick one product or combine multiple products in the same ad.</h2>
          </div>

          {loadingCatalog ? <p className="muted">Loading Coffee 2.0 products...</p> : null}
          {catalogError ? <p className="error-banner">{catalogError}</p> : null}

          <div className="product-toolbar">
            <span className="muted">
              {selectedProductIds.length
                ? `${selectedProductIds.length} product${selectedProductIds.length === 1 ? '' : 's'} selected`
                : 'No products selected yet'}
            </span>
            <div className="asset-strip">
              <button type="button" className="ghost-button" onClick={selectAllProducts}>
                Select all 4
              </button>
              <button type="button" className="ghost-button" onClick={clearProductSelection}>
                Clear
              </button>
            </div>
          </div>

          <div className="product-grid">
            {catalog.products.map((product: Product) => {
              const isSelected = selectedProductIds.includes(product.id)
              return (
                <button
                  key={product.id}
                  type="button"
                  className={`product-card ${isSelected ? 'selected' : ''}`}
                  aria-pressed={isSelected}
                  style={
                    {
                      '--card-start': product.palette[0],
                      '--card-mid': product.palette[1],
                      '--card-end': product.palette[2],
                    } as CSSProperties
                  }
                  onClick={() => toggleProductSelection(product.id)}
                >
                  <span className="product-name">{product.name}</span>
                  <span className="product-tagline">{product.tagline}</span>
                  <small className="card-meta">
                    {product.local_reference_count} local refs ready
                  </small>
                  <small className="card-meta">
                    {isSelected ? 'Included in this concept' : 'Tap to add to the lineup'}
                  </small>
                </button>
              )
            })}
          </div>

          {selectedProducts.length ? (
            <div className="product-details">
              <p className="product-description">
                {selectedProducts.length === 1
                  ? primarySelectedProduct?.description
                  : `Selected lineup: ${selectedProductNames.join(', ')}. The backend will combine the selected product positioning, benefits, and reference images into one campaign prompt.`}
              </p>
              <ul className="benefit-list">
                {selectedProductBenefits.slice(0, 6).map((benefit) => (
                  <li key={benefit}>{benefit}</li>
                ))}
              </ul>
              <p className="asset-note">
                Product folders loaded: <code>{selectedProductFolders.join(', ')}</code>
              </p>
              <p className="asset-note">
                Total local refs available: {totalSelectedProductRefs}. Best results usually
                come from 3 to 6 product photos per product: front packshot, 45 degree angle,
                close label detail, in-hand shot, and one lifestyle scene.
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
              <label className={`toggle-card ${isUgcAudioLocked ? 'locked' : ''}`}>
                <input
                  type="checkbox"
                  checked={isUgcAudioLocked ? true : includeAudio}
                  disabled={isUgcAudioLocked}
                  onChange={(event) => setIncludeAudio(event.target.checked)}
                />
                <span>
                  <strong>
                    {isUgcAudioLocked ? 'UGC audio locked on' : 'Generate native video audio'}
                  </strong>
                  <small>
                    {isUgcAudioLocked
                      ? 'UGC videos always render with speech enabled in the selected language, and the pipeline now creates a realistic starter frame before animating it.'
                      : 'Optional for cinematic ads. Turn it on when you want native dialogue or voiceover, but final premium voiceovers may still be cleaner from a dedicated voice tool.'}
                  </small>
                </span>
              </label>
            ) : null}

            <div className="field-block">
              <div className="prompt-row">
                <label className="field-label" htmlFor="prompt">
                  Custom prompt
                </label>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={handleSurprisePrompt}
                >
                  Surprise me
                </button>
              </div>
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
                and any shots you want to avoid. Video runs now generate a tailored starter
                frame first, then animate it for a stronger opening shot.
              </p>
              {surpriseHint ? <p className="surprise-hint">{surpriseHint}</p> : null}
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
              <span>
                {selectedProductNames.length
                  ? selectedProductNames.join(' + ')
                  : 'No products selected'}
              </span>
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
                    : 'Choose one or more products and submit your first prompt.'}
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
            {showCompletionBurst ? (
              <div className="completion-burst" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
            ) : null}
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
                    <strong>
                      {item.product_names?.length
                        ? item.product_names.join(' + ')
                        : item.product_name}
                    </strong>
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
