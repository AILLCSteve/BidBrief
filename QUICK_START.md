# Quick Start - Deploy to Render in 5 Minutes

## 🚀 Deploy Now

### 1. Create GitHub Repository

Go to GitHub and create a new repository:
- Name: `universal-doc-intelligence`
- Visibility: Private (recommended)
- **Do NOT** initialize with README

Copy your repository URL.

### 2. Push to GitHub

```bash
# Navigate to UniversalDocInt directory
cd "C:\Users\pr0ph\Documents\AI LLC\Apps\Doc Analysis Projects\DeployedDocAnalysisForMPT\UniversalDocInt"

# Add remote (replace with YOUR GitHub URL)
git remote add origin https://github.com/YOUR-USERNAME/universal-doc-intelligence.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### 3. Deploy to Render

1. Go to [render.com](https://render.com) → Sign in
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml` configuration
5. **Add environment variable:**
   - Key: `OPENAI_API_KEY`
   - Value: `sk-your-openai-api-key-here`
6. Click **"Create Web Service"**

**Done!** Your app will be live at `https://universal-doc-intelligence.onrender.com`

---

## 📋 What's Included

✅ Complete HOTDOG AI architecture (3,732 LOC)
✅ Flask web app (25+ API endpoints)
✅ Multi-format document extraction
✅ Real-time progress tracking
✅ Excel dashboard exports
✅ Production-ready configuration
✅ Automatic deployment (render.yaml)

---

## 📚 Full Documentation

- **Deployment Guide:** See `DEPLOYMENT.md` (complete step-by-step)
- **Platform Docs:** See `README.md` (API, usage, architecture)
- **Branding Guide:** See `shared/BRANDING_README.md` (customization)
- **Extraction Summary:** See `EXTRACTION_SUMMARY.md` (what was copied)

---

## 🔧 Environment Variables (Render Dashboard)

**Required:**
```
OPENAI_API_KEY=sk-your-key-here
```

**Optional (Authentication):**
```
AUTH_USER1_EMAIL=admin@example.com
AUTH_USER1_PASSWORD=your-secure-password
AUTH_USER1_NAME=Admin User
```

**Auto-Generated:**
- `SECRET_KEY` ✅
- `PORT` ✅
- `PYTHON_VERSION` ✅

---

## ✅ Repository Status

**Current Status:**
```
✅ Git initialized
✅ 2 commits created
✅ 28 files tracked
✅ All documentation included
✅ render.yaml configured
✅ Ready to push
```

**Commits:**
1. `76768d1` - Initial commit: Complete HOTDOG AI platform
2. `f7e288e` - Add comprehensive deployment guide

---

## 🎯 Next Steps After Deployment

1. **Test the application** (upload PDF, run analysis)
2. **Customize branding** (colors, logo, text)
3. **Configure questions** (edit `config/default_questions.json`)
4. **Set up custom domain** (optional)
5. **Enable authentication** (optional)

---

**Ready to deploy!** Follow the 3 steps above to go live.
