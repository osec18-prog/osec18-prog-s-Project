# CampusConnect+ Deployment Plan ✅

## Phase 1: Backend Deployment Files (Flask → Render) ✅
- [x] 1. Create `requirements.txt` — Python dependencies
- [x] 2. Create `runtime.txt` — Python version
- [x] 3. Create `Procfile` — Render start command
- [x] 4. Create `render.yaml` — Render infrastructure config
- [x] 5. Create `init_db.py` — Database initialization script
- [x] 6. Modify `app.py` — Production config (port from env, CORS, serve Flutter web)

## Phase 2: Flutter Web Compatibility ✅
- [x] 7. Create `scan_screen_web.dart` — Web-compatible QR scan placeholder (no camera)
- [x] 8. Create `scan_screen_mobile.dart` — Mobile scanner (renamed from original)
- [x] 9. Create `scan_screen.dart` — Conditional import for web vs mobile
- [x] 10. Modify `main.dart` — Auto-detect server URL on web from window origin

## Phase 3: Documentation ✅
- [x] 11. Created `DEPLOYMENT_GUIDE.md` — Complete step-by-step deployment guide

## Deployment Steps (You Do)
- [ ] Build Flutter Web: `cd campusconnect_app && flutter build web --base-href=/app/`
- [ ] Copy build: `xcopy /E /I campusconnect_app\build\web\* static\flutter_app\`
- [ ] Initialize DB: `python init_db.py`
- [ ] Push to GitHub
- [ ] Deploy on Render via GitHub
- [ ] Test all URLs
