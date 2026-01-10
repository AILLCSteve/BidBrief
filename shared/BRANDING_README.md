# Branding Assets - Universal Document Intelligence

This directory contains shared branding assets for the Universal Document Intelligence Platform. All assets are generic and ready for customization with client branding.

## Quick Customization Guide

### 1. Update Colors (CSS Variables)

Edit `assets/css/common.css`:

```css
:root {
    --brand-primary: #667eea;       /* Main brand color */
    --brand-secondary: #764ba2;     /* Secondary brand color */
    --brand-accent: #9F7AEA;        /* Accent highlights */
}
```

### 2. Replace Logo

Replace the placeholder logo with your client's logo:
- **File location:** `assets/images/logo.png`
- **Recommended size:** 200x60px or maintain similar aspect ratio
- **Format:** PNG with transparent background or SVG

### 3. Update Application Name

In `index.html`:
- Page title (line 6): Change "Universal Document Analyzer" to your client's name
- Header H1 (line 326): Update main heading
- Navbar title (line 319): Update navigation brand name

### 4. Customize Background

The default background is a CSS gradient. To use a custom image:

In `index.html`, find the `body::before` style and replace:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

With:
```css
background-image: url('/shared/assets/images/your-background.jpg');
```

## File Structure

```
shared/
├── BRANDING_README.md (this file)
└── assets/
    ├── css/
    │   └── common.css          # Shared styles with CSS variables
    └── images/
        └── logo.png            # Placeholder logo (replace with client logo)
```

## Branding Checklist

When customizing for a new client:

- [ ] Update CSS color variables in `common.css`
- [ ] Replace `logo.png` with client logo
- [ ] Update page title in `index.html`
- [ ] Update header and navbar text in `index.html`
- [ ] Update service name in `app.py` (line 296: health check)
- [ ] Update configuration name in `config/default_questions.json`
- [ ] Test on all devices (desktop, tablet, mobile)
- [ ] Verify color contrast for accessibility

## Color Scheme Options

### Professional Blue (Current)
```css
--brand-primary: #1E3A8A;
--brand-secondary: #3B82F6;
```

### Modern Purple (Default)
```css
--brand-primary: #667eea;
--brand-secondary: #764ba2;
```

### Corporate Green
```css
--brand-primary: #059669;
--brand-secondary: #10B981;
```

### Elegant Dark
```css
--brand-primary: #1F2937;
--brand-secondary: #4B5563;
```

## Support

For questions about branding customization, refer to the main `README.md` or contact the development team.

---

**Platform:** Universal Document Intelligence v1.0
**Last Updated:** 2026-01-10
