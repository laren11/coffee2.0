# Coffee 2.0 AI Content Creator

A React + Django MVP for generating Coffee 2.0 branded image ads, ad videos, and UGC-style videos with `fal.ai`.

## What is in the MVP

- Login-protected app using Django token auth
- Default test user bootstrap support
- Product picker for `Coffee 2.0`, `Refresh 2.0`, `Matcha 2.0`, and `Collagen 2.0`
- Image or video generation
- Two video styles:
  - `UGC`
  - `Ad`
- Safe UGC creator presets
- Optional local asset folders for product photos and creator photos
- Optional manual upload of extra reference photos
- Async `fal.ai` job submission and polling
- Render deployment wiring with `render.yaml`

## Current model strategy

The app automatically chooses the model based on the job type:

- Image without references: `fal-ai/nano-banana-pro`
- Image with references: `fal-ai/nano-banana-pro/edit`
- Video without references: `fal-ai/veo3.1`
- UGC video with 2+ reference images: `fal-ai/veo3.1/reference-to-video`
- Ad video with references: `fal-ai/veo3.1/image-to-video` after a generated cinematic opening frame

This is a good MVP balance between quality, cost, and brand control.

## Login

The app is now protected. API access requires a valid token, and the frontend shows a sign-in screen first.

Default local test credentials:

- Username: `coffee`
- Password: `coffe20`

Create or refresh that user locally with:

```powershell
cd backend
python manage.py ensure_default_user
```

Create a different user manually if you want:

```powershell
cd backend
python manage.py ensure_default_user --username myuser --password mypass
```

## Where to add product photos

Put product photos here:

- `backend/assets/products/coffee-2-0/`
- `backend/assets/products/refresh-2-0/`
- `backend/assets/products/matcha-2-0/`
- `backend/assets/products/collagen-2-0/`

The app auto-loads those images during generation.

## Where to add UGC creator photos

Put rights-cleared creator photos here:

- `backend/assets/ugc-creators/assertive-founder/`
- `backend/assets/ugc-creators/wellness-mentor/`
- `backend/assets/ugc-creators/performance-creator/`

Important:

- Only use photos you own or have permission to use.
- Do not use scraped internet photos or public figure likenesses.

## Local setup

### Backend

```powershell
cd backend
python manage.py migrate
python manage.py ensure_default_user
python manage.py runserver
```

The API runs on `http://127.0.0.1:8000`.

### Frontend

```powershell
cd frontend
npm.cmd run dev
```

The frontend runs on `http://127.0.0.1:5173`.

## Environment files

- Backend local env: `backend/.env`
- Backend template: `backend/.env.example`
- Frontend template: `frontend/.env.example`

## Render deployment

This repo now includes `render.yaml`, which creates:

- `coffee-20-api` as a free Python web service
- `coffee-20-frontend` as a free static site
- `coffee-20-db` as a free Render Postgres database

### What you need to do in Render

1. Push this repo to GitHub.
2. In Render, create a new Blueprint and point it at the repo.
3. During setup, fill in the secret placeholders:
   - `FAL_KEY`
   - `DEFAULT_TEST_PASSWORD`
   - `DJANGO_CORS_ALLOWED_ORIGINS`
   - `DJANGO_CSRF_TRUSTED_ORIGINS`
   - `VITE_API_BASE_URL`
4. Use your frontend Render URL as:
   - `DJANGO_CORS_ALLOWED_ORIGINS`
   - `DJANGO_CSRF_TRUSTED_ORIGINS`
5. Use your backend Render URL plus `/api` as:
   - `VITE_API_BASE_URL`

### Recommended values after the services exist

If Render gives you URLs like:

- Frontend: `https://coffee-20-frontend.onrender.com`
- Backend: `https://coffee-20-api.onrender.com`

Then set:

- `DJANGO_CORS_ALLOWED_ORIGINS=https://coffee-20-frontend.onrender.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://coffee-20-frontend.onrender.com`
- `VITE_API_BASE_URL=https://coffee-20-api.onrender.com/api`
- `DEFAULT_TEST_PASSWORD=coffe20`

The backend build step already runs:

- `python manage.py migrate`
- `python manage.py ensure_default_user`

So the default login is recreated automatically on deploy.

## Verified commands

Backend:

```powershell
cd backend
python manage.py test
python manage.py check
python manage.py migrate
```

Frontend:

```powershell
cd frontend
npm.cmd run build
```

## Notes on UGC creators

I did not wire real-person or internet-scraped likeness generation into the product. Instead, the app now supports:

- safe creator presets
- local creator asset folders
- prompt-based creator direction

If you want a specific human look, add rights-cleared photos for that creator into the matching folder and I can tighten those presets further.
