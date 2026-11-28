<div align="center">

# ✂️ Wonder Clips

### Turn long videos into viral clips.

**Free, private AI video clipper that runs on your own computer.**
Paste a YouTube or Instagram link, or upload a video up to 30 minutes, and get up to **8 ready-to-post vertical (9:16) clips** with captions and face tracking.

<br />

[![Use It Now](https://img.shields.io/badge/🚀_USE_IT_NOW-clips.wondermayank.in-573AFC?style=for-the-badge)](https://clips.wondermayank.in/)
[![Free](https://img.shields.io/badge/100%25-FREE-2ea44f?style=for-the-badge)](https://clips.wondermayank.in/)
[![Private](https://img.shields.io/badge/PRIVATE-RUNS_ON_YOUR_PC-0A84FF?style=for-the-badge)](#-privacy)

[![Website](https://img.shields.io/badge/🌐_WONDERMAYANK.IN-1f2937?style=for-the-badge)](https://wondermayank.in/)
[![Contact](https://img.shields.io/badge/✉️_CONTACT-1f2937?style=for-the-badge)](https://wondermayank.in/contact)
[![Issues](https://img.shields.io/badge/🐞_REPORT_A_BUG-1f2937?style=for-the-badge)](https://github.com/wondermayank/wonderclip/issues)

<br />

[![Tech](https://skillicons.dev/icons?i=nextjs,react,tailwind,py,fastapi,cloudflare)](#-built-with)

<br />

⭐ **If this helps you, please star the repo!** ⭐

</div>

---

## 📚 Quick links

| I want to... | Go to |
| --- | --- |
| 🎬 **Use** Wonder Clips | [For users](#-for-users-use-it) |
| 🏠 **Host** my own copy | [Host it yourself](#-host-it-yourself) |
| 🧑‍💻 **Develop** it locally | [Run locally](#-run-locally-for-development) |

## ✨ What it does

| | Feature | Details |
| :-: | --- | --- |
| 🔗 | **Link or upload** | Paste a YouTube or Instagram link, or upload a video up to 30 minutes |
| 🧠 | **Finds the best moments** | AI transcribes the video and picks the most engaging parts |
| 💬 | **Captions** | Adds captions automatically |
| 🙂 | **Face tracking** | Follows the speaker's face so they stay in frame |
| 📱 | **Vertical clips** | Up to 8 ready-to-post 9:16 clips (Reels, Shorts, TikTok) |
| 🔒 | **Private** | Everything runs on your own PC |

## 🔒 Privacy

- 🖥️ The AI work happens on **your computer**, not on a server
- 🚫 Your videos **never leave your PC**
- 🗑️ Videos are **deleted after 72 hours**
- 🛡️ The engine only accepts requests from the website address you allow

## ⚙️ How it works

```text
 your browser                          your own Windows PC
┌───────────────────────┐   127.0.0.1   ┌──────────────────────────────┐
│ clips.wondermayank.in │ ───────────▶  │ Wonder Clips engine          │
│ (static website)      │ ◀───────────  │ transcribe · find highlights │
└───────────────────────┘               │ · track face · caption · cut │
                                        └──────────────────────────────┘
```

- The **website** (`web/`) is a static site. It only shows the interface.
- The **engine** (`engine/`) runs on the user's own PC and does all the AI work.

---

## 🎬 For users (use it)

1. Open **[clips.wondermayank.in](https://clips.wondermayank.in/)**
2. Press **Download installer for Windows** and double-click `Install-WonderClips.bat` (about 5 to 15 minutes, about 4 GB).
   Or paste this in PowerShell:

   ```powershell
   irm https://raw.githubusercontent.com/wondermayank/wonderclip/main/engine/install.ps1 | iex
   ```

3. Start **Wonder Clips** from your Desktop. If the browser asks to allow "access apps on this device", choose **Allow**.
4. Add a video and get your clips! 🎉

### 💻 Requirements

| | Needed |
| --- | --- |
| OS | Windows 10 or 11 (64-bit) |
| Disk space | About 8 GB free |
| GPU | NVIDIA GPU with 6 GB or more for best speed |
| No GPU? | It also works on the CPU, just slower |

> ⚠️ Only clip videos you own or have permission to use.

---

## 🏠 Host it yourself

You can run your own Wonder Clips under your own name and domain. There are two parts: the **website** (hosted online, free) and the **engine** (runs on each user's PC).

### 1️⃣ Fork the repo

Fork this repo to your GitHub account. The repo name `wonderclip` is used in the links below, so change them if you rename it.

### 2️⃣ Deploy the website on Cloudflare Pages (free)

Most settings are already in the repo: `web/wrangler.toml` (project name, output folder, compatibility date) and `web/.node-version` (Node 22). Security and cache headers are in `web/public/_headers`.

<details>
<summary><b>☁️ Option A: connect GitHub (auto-deploys on every push)</b></summary>

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → pick your fork.
2. Fill in only these two fields:

   | Setting | Value |
   | --- | --- |
   | Root directory | `web` |
   | Build command | `npm run build` |

   Everything else (output directory `out`, Node version) is picked up from the repo.
3. Deploy, then add your own domain under **Custom domains** (for example `clips.yourname.com`).

</details>

<details>
<summary><b>💻 Option B: deploy from your computer with Wrangler</b></summary>

```bash
cd web
npm install
npx wrangler login      # one time
npm run deploy          # builds the site and uploads it to Cloudflare Pages
```

If you rename the project, change `name` in `web/wrangler.toml` and `--project-name` in the `deploy` script in `web/package.json`.

</details>

<details>
<summary><b>▲ Other hosts (Vercel, Netlify, GitHub Pages)</b></summary>

Use root directory `web`, build command `npm run build` and output directory `out`.

</details>

### 3️⃣ Point the engine at your site

The engine blocks every website except the ones you allow. Edit `cors_origins` in `engine/backend/app/config.py`:

```python
cors_origins = ("https://clips.yourname.com", "http://localhost:3000", "http://127.0.0.1:3000")
```

### 4️⃣ Update your links

| File | What to change |
| --- | --- |
| `web/lib/site.ts` | Your site URL, GitHub repo and install command |
| `web/public/Install-WonderClips.bat` | Replace `wondermayank/wonderclip` with `your-username/your-repo` |
| `engine/install.ps1` | Replace `wondermayank/wonderclip` with `your-username/your-repo` |
| `engine/scripts/start_wonderclip.ps1` | The default `$Url` that opens after the engine starts |

Commit and push. Cloudflare redeploys automatically, and the installer now installs **your** version of the engine. ✅

---

## 🧑‍💻 Run locally for development

```bash
# website
cd web
npm install
npm run dev          # http://localhost:3000
```

```bash
# engine (Python 3.12)
cd engine/backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --port 8000
```

## 🗂️ Project structure

```text
web/       Next.js static website (Cloudflare Pages: root directory = web)
engine/    Local engine (FastAPI backend, install.ps1 and start/stop scripts)
LICENSE-MIT, LICENSE-APACHE, NOTICE    License files
```

## 🧰 Built with

Next.js, React, Tailwind CSS, FastAPI, FFmpeg, faster-whisper, MediaPipe, Ollama (Qwen3) and yt-dlp. Each of these keeps its own license.

## 📜 License and credit

The code is **dual-licensed**. You can use it under either of:

- [MIT License](LICENSE-MIT)
- [Apache License 2.0](LICENSE-APACHE)

at your option. Both let you use, modify and share the code, but you **must keep the copyright notice and license** in every copy. If you pick Apache-2.0, you must also keep the [NOTICE](NOTICE) file.

If you use or fork this project, please give credit:

> Based on [Wonder Clips](https://github.com/wondermayank/wonderclip) by [Wondermayank](https://wondermayank.in/)

The tools listed in [Built with](#-built-with) keep their own licenses.

## 📬 Contact

[![Website](https://img.shields.io/badge/WEBSITE-wondermayank.in-573AFC?style=for-the-badge)](https://wondermayank.in/)
[![Contact](https://img.shields.io/badge/CONTACT-wondermayank.in/contact-1f2937?style=for-the-badge)](https://wondermayank.in/contact)
[![Issues](https://img.shields.io/badge/OPEN_AN_ISSUE-GitHub-181717?style=for-the-badge&logo=github)](https://github.com/wondermayank/wonderclip/issues)

<div align="center">

Made with ❤️ in India by **[Wondermayank](https://wondermayank.in/)**

</div>
