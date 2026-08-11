# Vercel Preview

This frontend can be connected to Vercel as a preview-only deployment.

## Suggested Vercel settings

- Root directory: `frontend`
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`

## Routing

`frontend/vercel.json` rewrites non-`/api` paths back to `index.html`, so direct visits and refreshes on SPA routes keep working.

## What Preview does

- Shows the frontend build for PR review
- Produces a unique Preview URL for authorized PRs
- Keeps `/api` requests visible as backend-unavailable instead of faking a backend

## Limits

- It does not deploy FastAPI, SQLite, or any full-stack backend
- Fork PR preview availability depends on Vercel authorization
- Preview does not replace CI or `make check`
- Secrets must stay in Vercel settings, not in this repository
