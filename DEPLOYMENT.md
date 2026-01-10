# Deployment Guide - Universal Document Intelligence Platform

Complete step-by-step instructions for deploying to Render.com.

---

## 📋 Prerequisites

- [x] Git repository initialized (✅ Complete)
- [ ] GitHub account
- [ ] Render.com account (free tier available)
- [ ] OpenAI API key (with GPT-4o access)

---

## 🚀 Quick Deploy (5-10 minutes)

### Step 1: Create GitHub Repository

1. **Go to GitHub** and create a new repository:
   - Repository name: `universal-doc-intelligence` (or your preferred name)
   - Visibility: Private (recommended) or Public
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)

2. **Copy the repository URL** (you'll need it next)
   - Format: `https://github.com/YOUR-USERNAME/universal-doc-intelligence.git`

### Step 2: Push to GitHub

Open terminal in the `UniversalDocInt` directory and run:

```bash
# Add GitHub as remote origin (replace with YOUR repository URL)
git remote add origin https://github.com/YOUR-USERNAME/universal-doc-intelligence.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Verify:** Visit your GitHub repository to confirm all files are uploaded.

### Step 3: Deploy to Render

#### 3a. Connect GitHub to Render

1. **Go to [Render.com](https://render.com)** and sign in
2. Click **"New +"** → **"Web Service"**
3. Click **"Connect GitHub"** (if not already connected)
4. Grant Render access to your repositories
5. Find and select `universal-doc-intelligence` repository

#### 3b. Configure Web Service

Render will auto-detect the `render.yaml` configuration. Verify these settings:

| Setting | Value |
|---------|-------|
| **Name** | `universal-doc-intelligence` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn --config gunicorn_config.py app:app` |
| **Plan** | Starter (or Free for testing) |

#### 3c. Set Environment Variables

In the Render dashboard, add these environment variables:

**Required:**
```
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**Auto-Generated (by Render):**
- `SECRET_KEY` - Auto-generated secure key ✅
- `PORT` - Auto-set by Render ✅
- `PYTHON_VERSION` - Set to 3.9 ✅

**Optional (for authentication):**
```
AUTH_USER1_EMAIL=admin@example.com
AUTH_USER1_PASSWORD=your-secure-password
AUTH_USER1_NAME=Admin User
```

#### 3d. Deploy

1. Click **"Create Web Service"**
2. Render will:
   - Clone your repository
   - Install dependencies
   - Start the application
   - Provide a public URL (e.g., `https://universal-doc-intelligence.onrender.com`)

**Deployment time:** ~3-5 minutes for first deploy

### Step 4: Verify Deployment

1. **Wait for build to complete** (watch logs in Render dashboard)
2. **Click the URL** provided by Render
3. **Test the application:**
   - Upload a PDF document
   - Start an analysis
   - Verify real-time progress updates
   - Check export functionality

---

## 🔧 Configuration

### OpenAI API Key

**Where to get it:**
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Navigate to **API Keys**
3. Create new secret key
4. **Important:** Ensure you have GPT-4o access (requires paid tier)

**Add to Render:**
1. Go to your web service in Render
2. Click **"Environment"** tab
3. Add `OPENAI_API_KEY` with your key
4. Click **"Save Changes"** (this will redeploy)

### Custom Domain (Optional)

1. In Render dashboard, go to **"Settings"** → **"Custom Domain"**
2. Add your domain (e.g., `analyzer.yourdomain.com`)
3. Update DNS records (Render provides instructions)
4. SSL certificate is automatically provisioned

---

## 🔄 Updates and Redeployment

### Automatic Deployment

Render automatically redeploys when you push to GitHub:

```bash
# Make changes to your code
git add .
git commit -m "Description of changes"
git push origin main
```

Render will detect the push and redeploy automatically (2-3 minutes).

### Manual Deployment

In Render dashboard:
1. Go to your web service
2. Click **"Manual Deploy"** → **"Deploy latest commit"**

---

## 🐛 Troubleshooting

### Build Fails

**Check logs in Render dashboard:**
- Common issue: Missing dependencies in `requirements.txt`
- Solution: Add missing package and push update

### Application Won't Start

**Check environment variables:**
```bash
# In Render logs, verify:
- OPENAI_API_KEY is set
- SECRET_KEY is generated
- PORT is set correctly
```

### OpenAI API Errors

**Check API key:**
1. Verify key is correct in Render environment variables
2. Ensure GPT-4o access is enabled
3. Check API usage limits and billing

### Timeout Errors

**Increase timeout settings:**
- Already configured in `gunicorn_config.py` (900 seconds / 15 minutes)
- For larger documents, consider upgrading Render plan (more memory/CPU)

### Session Flickering/Loss

**Already resolved:**
- Using single worker configuration (`workers = 1`)
- Threading enabled (`threads = 10`)
- Max requests disabled (`max_requests = 0`)

---

## 📊 Monitoring

### Logs

**View real-time logs:**
1. Render dashboard → Your web service
2. Click **"Logs"** tab
3. Filter by severity (Info, Warning, Error)

### Health Check

**Endpoint:** `https://your-app.onrender.com/health`

**Expected response:**
```json
{
  "status": "ok",
  "service": "Universal Document Intelligence",
  "timestamp": "2026-01-10T..."
}
```

### Admin Dashboard

**Access:** `https://your-app.onrender.com/admin-sessions`

**Features:**
- View all analysis sessions
- Monitor active/completed analyses
- Check progress and status

---

## 💰 Cost Estimates

### Render Hosting

| Plan | Cost | Features |
|------|------|----------|
| **Free** | $0/mo | 750 hrs/mo, sleeps after inactivity, 512MB RAM |
| **Starter** | $7/mo | Always on, 512MB RAM, SSL included |
| **Standard** | $25/mo | 2GB RAM, better performance |

**Recommendation:** Starter plan for production use.

### OpenAI API

| Document Size | Estimated Cost |
|--------------|----------------|
| 10 pages | $0.50 - $1.00 |
| 50 pages | $2.00 - $4.00 |
| 100 pages | $5.00 - $8.00 |

*Based on GPT-4o pricing and 105-question default analysis*

---

## 🔒 Security Best Practices

### Environment Variables

- ✅ Never commit `.env` files to git (already in `.gitignore`)
- ✅ Use Render's environment variable management
- ✅ Rotate API keys regularly

### Authentication

**Enable optional password protection:**

In Render environment variables:
```
AUTH_USER1_EMAIL=admin@example.com
AUTH_USER1_PASSWORD=strong-secure-password-here
AUTH_USER1_NAME=Admin User
```

Users will see a login form before accessing the analyzer.

### SSL/HTTPS

- ✅ Automatically enabled by Render
- ✅ Free SSL certificates (Let's Encrypt)
- ✅ Auto-renewal

---

## 📈 Scaling

### Vertical Scaling (More Power)

Upgrade Render plan for:
- More RAM (handle larger documents)
- More CPU (faster processing)
- Higher concurrency

### Horizontal Scaling (More Workers)

**Current configuration:** Single worker with threading

**To enable multiple workers:**

1. Update `gunicorn_config.py`:
   ```python
   workers = 2  # Or more
   ```

2. **⚠️ Important:** Requires database for session management
   - Current: In-memory (single worker only)
   - Upgrade: PostgreSQL/Redis for multi-worker support
   - See: `PERSISTENT_STORAGE_MIGRATION_PLAN.md` (if included)

---

## 🎯 Next Steps

After successful deployment:

1. **Test thoroughly:**
   - Upload various PDF sizes
   - Test all export formats
   - Verify real-time progress
   - Check error handling

2. **Customize branding:**
   - See `shared/BRANDING_README.md`
   - Update colors, logo, text
   - Redeploy with `git push`

3. **Configure questions:**
   - Edit `config/default_questions.json`
   - Add/remove sections
   - Customize for your use case

4. **Monitor usage:**
   - Check Render logs regularly
   - Monitor OpenAI API usage/costs
   - Set up alerts (Render Pro feature)

---

## 📞 Support

### Resources

- **Documentation:** See `README.md` for full platform docs
- **Branding:** See `shared/BRANDING_README.md`
- **Architecture:** See `EXTRACTION_SUMMARY.md`

### Getting Help

- **Render Support:** [render.com/docs](https://render.com/docs)
- **OpenAI Support:** [platform.openai.com](https://platform.openai.com/)
- **Repository Issues:** (Your GitHub Issues page)

---

## ✅ Deployment Checklist

Use this checklist to ensure successful deployment:

- [ ] GitHub repository created
- [ ] Code pushed to GitHub (`git push origin main`)
- [ ] Render account created
- [ ] GitHub connected to Render
- [ ] Web service created in Render
- [ ] `OPENAI_API_KEY` environment variable set
- [ ] Deployment completed successfully (check logs)
- [ ] Application accessible via Render URL
- [ ] Health check endpoint responding (`/health`)
- [ ] Test PDF upload and analysis
- [ ] Verify real-time progress updates
- [ ] Test export functionality (Excel, CSV, JSON)
- [ ] (Optional) Custom domain configured
- [ ] (Optional) Authentication enabled
- [ ] (Optional) Monitoring/alerts set up

---

## 🎉 Success!

Your Universal Document Intelligence Platform is now live and ready for production use.

**Your deployment URL:** `https://your-app-name.onrender.com`

**What's working:**
- ✅ 7-layer HOTDOG AI architecture
- ✅ Multi-format document extraction
- ✅ Real-time progress tracking
- ✅ Excel dashboard exports
- ✅ Session management
- ✅ Production-ready configuration

**Next:** Customize branding and question sets for your specific use case.

---

**Generated:** 2026-01-10
**Platform:** Universal Document Intelligence
**Deployment:** Render.com
**Status:** Production Ready ✅
