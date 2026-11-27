# Wonder Clips

**Turn long videos into viral clips. Free, private, and it runs on your own computer.**

Wonder Clips is an AI video clipper made by [Mayank (wondermayank)](https://wondermayank.in). Paste a YouTube or Instagram link, or upload a video up to 30 minutes. It finds the best moments, adds captions, follows the speaker's face and gives you up to 8 ready-to-post vertical (9:16) clips.

**Use it now: https://clips.wondermayank.in**

---

## How it works

```
 your browser                          your own Windows PC
┌──────────────────────┐   127.0.0.1   ┌────────────────────────────┐
│ clips.wondermayank.in │ ───────────▶ │ Wonder Clips engine         │
│ (static website)      │ ◀─────────── │ transcribe · find highlights │
└──────────────────────┘               │ · track face · caption · cut │
                                        └────────────────────────────┘
```

- The **website** (`web/`) is a static site. It only shows the interface.
- The **engine** (`engine/`) runs on the user's own PC and does all the AI work. Videos never leave the computer and are deleted after 72 hours.
- The engine accepts requests only from the website address listed in `engine/backend/app/config.py`.

## For users

1. Open https://clips.wondermayank.in
2. Press **Download installer for Windows** and double-click `Install-WonderClips.bat` (about 5 to 15 minutes, about 4 GB).
   Or paste this in PowerShell:
   ```powershell
   irm https://raw.githubusercontent.com/wondermayank/wonderclip/main/engine/install.ps1 | iex
   ```
3. Start **Wonder Clips** from your Desktop. If the browser asks to allow "access apps on this device", choose **Allow**.
4. Add a video and get your clips.

Needs Windows 10 or 11 (64-bit), about 8 GB of free disk space and an NVIDIA GPU with 6 GB or more for best speed (it also works on the CPU, just slower).

## Set up your own copy

You can run your own Wonder Clips under your own name and domain.

### 1. Fork and rename
Fork this repo to your GitHub account (the repo name `wonderclip` is used in the links below, so change them if you rename it).

### 2. Deploy the website on Cloudflare Pages (free)
Most settings are already in the repo: `web/wrangler.toml` (project name, output folder, compatibility date) and `web/.node-version` (Node 22). Security and cache headers are in `web/public/_headers`.

**Option A: connect GitHub (auto-deploys on every push)**
1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → pick your fork.
2. Fill in only these two fields (Cloudflare cannot read them from a file):

   | Setting | Value |
   |---|---|
   | Root directory | `web` |
   | Build command | `npm run build` |

   Everything else (output directory `out`, Node version) is picked up from the repo.
3. Deploy, then add your own domain under **Custom domains** (for example `clips.yourname.com`).

**Option B: deploy from your computer with Wrangler**
```bash
cd web
npm install
npx wrangler login      # one time
npm run deploy          # builds the site and uploads it to Cloudflare Pages
```
If you rename the project, change `name` in `web/wrangler.toml` and `--project-name` in the `deploy` script in `web/package.json`.

Other static hosts work too (Vercel, Netlify, GitHub Pages): use root directory `web`, build command `npm run build` and output directory `out`.

### 3. Point the engine at your site
The engine blocks every website except the ones you allow. Edit `cors_origins` in `engine/backend/app/config.py`:

```python
cors_origins = ("https://clips.yourname.com", "http://localhost:3000", "http://127.0.0.1:3000")
```

### 4. Update your links
- `web/lib/site.ts`: your site URL, GitHub repo and install command.
- `web/public/Install-WonderClips.bat` and `engine/install.ps1`: replace `wondermayank/wonderclip` with `your-username/your-repo`.
- `engine/scripts/start_clipmitra.ps1`: the default `$Url` that opens after the engine starts.

Commit and push. Cloudflare redeploys automatically, and the installer now installs your version of the engine.

### 5. Run it locally for development
```powershell
# website
cd web
npm install
npm run dev          # http://localhost:3000

# engine (Python 3.12)
cd engine/backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --port 8000
```

## Project structure

```
web/       Next.js static website (Cloudflare Pages: root directory = web)
engine/    Local engine (FastAPI backend, install.ps1 and start/stop scripts)
```

## Built with

Next.js, React, Tailwind CSS, FastAPI, FFmpeg, faster-whisper, MediaPipe, Ollama (Qwen3) and yt-dlp.

## Contact

Made by **Mayank** · [wondermayank.in](https://wondermayank.in) · [Contact](https://wondermayank.in/contact) · [Open an issue](https://github.com/wondermayank/wonderclip/issues)
