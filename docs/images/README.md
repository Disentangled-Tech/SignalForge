# Screenshots for user documentation

This folder holds screenshots used in [USER_GUIDE.md](../USER_GUIDE.md) and [USER_ONBOARDING.md](../USER_ONBOARDING.md).

## Adding or updating screenshots

1. Run the app locally: `make dev` (or your deployment).
2. Log in and navigate to the screen you want to capture.
3. Capture a screenshot (browser dev tools, OS screenshot tool, or Cursor’s screenshot).
4. Save as PNG in this folder using the filenames referenced in the docs, for example:
   - `screenshot-login.png` — Login page
   - `screenshot-companies-list.png` — Companies list with nav
   - `screenshot-companies-add.png` — Add company form
   - `screenshot-companies-import.png` — Import companies (CSV/JSON)
   - `screenshot-company-detail.png` — Company detail with outreach section
   - `screenshot-briefing.png` — Daily briefing page
   - `screenshot-scout-list.png` — Scout runs list
   - `screenshot-scout-new.png` — New Scout run form
   - `screenshot-settings.png` — Settings page
   - `screenshot-bias-reports.png` — Bias reports list

5. Keep file size reasonable (e.g. under 500 KB); crop to the main content area if needed.

If an image is missing, the doc will show broken image links until you add the file.
