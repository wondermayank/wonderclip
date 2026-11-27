import { EngineGate } from "@/components/EngineGate";
import { UploadCard } from "@/components/UploadCard";
import { Reveal } from "@/components/Reveal";
import { RotatingWord } from "@/components/RotatingWord";
import { ArrowRightIcon, BoltIcon, CcIcon, FrameIcon, LayersIcon, ScissorsIcon, SparkIcon, UploadIcon } from "@/components/icons";
import { SITE } from "@/lib/site";

const FEATURES = [
  { Icon: ScissorsIcon, tint: "bg-[#D9CCFF] text-[#3E2A9E]", title: "Finds the best moments", body: "AI reads the whole video and picks the parts people will actually watch." },
  { Icon: CcIcon, tint: "bg-[#C7DDFF] text-[#1F4FA3]", title: "Adds captions", body: "Word-by-word captions in Hinglish or Devanagari, with bold, karaoke or minimal styles." },
  { Icon: FrameIcon, tint: "bg-[#CDEFD9] text-[#1E6B3B]", title: "Reframes to 9:16", body: "Follows the speaker's face so every clip fits Reels, Shorts and TikTok." },
  { Icon: BoltIcon, tint: "bg-[#FFE0CC] text-[#9A4A12]", title: "Up to 8 clips", body: "From a video up to 30 minutes. Trim, restyle and export in one place." },
];

const STEPS = [
  { Icon: UploadIcon, title: "Add your video", body: "Upload a file, or paste a YouTube, Instagram or other link." },
  { Icon: SparkIcon, title: "AI does the work", body: "It finds highlights, adds captions and follows the speaker. Nothing leaves your PC." },
  { Icon: LayersIcon, title: "Download your clips", body: "Edit if you like, then export ready-to-post vertical clips." },
];

const CHIPS = ["Runs on your own PC", "Free, no sign-up", "No watermark"];

const QUICK = [
  { q: "Are my videos uploaded anywhere?", a: "No. Everything runs on your own computer. Files are deleted automatically after 72 hours." },
  { q: "What do I need?", a: "Windows 10 or 11, about 8 GB of free disk space and a one-time ~4 GB download. An NVIDIA GPU with 6 GB or more is best, but a normal processor works too, just slower." },
  { q: "Why do I have to install something?", a: "The AI is heavy, so it runs on your computer instead of a server. That is why Wonder Clips is free and private." },
];

export default function CreateClipsPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 pb-10 pt-8 sm:px-8 lg:pt-14">
      {/* ---------- hero ---------- */}
      <section className="grid items-center gap-10 lg:grid-cols-[1.05fr_1fr] lg:gap-14">
        <div>
          <h1 className="text-4xl font-extrabold leading-[1.08] tracking-tight text-zinc-900 sm:text-5xl lg:text-6xl">
            Turn long videos into <RotatingWord words={["viral", "captioned", "vertical", "ready-to-post"]} /> clips
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-zinc-600">
            Paste a link or upload a video. Wonder Clips finds the best moments, adds captions and reframes the speaker, all on your own computer.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <a href="#studio" className="inline-flex items-center gap-2 rounded-full bg-[#573AFC] px-6 py-3.5 font-semibold text-white shadow-[0_12px_30px_-10px_rgba(87,58,252,.7)] transition hover:-translate-y-0.5 hover:brightness-110">
              Start clipping <ArrowRightIcon width={18} height={18} />
            </a>
            <a href="#how" className="inline-flex items-center rounded-full bg-[#ECE6FF] px-6 py-3.5 font-semibold text-[#3E2A9E] transition hover:bg-[#E2D9FF]">How it works</a>
          </div>
          <ul className="mt-7 flex flex-wrap gap-2.5">
            {CHIPS.map((c) => (
              <li key={c} className="rounded-full bg-[#F1EDFF] px-4 py-2 text-sm font-medium text-zinc-700">✓ {c}</li>
            ))}
          </ul>
        </div>
        <div className="relative">
          <div className="absolute -inset-4 -z-10 rounded-[40px] bg-gradient-to-br from-[#D9CCFF] via-[#C7DDFF] to-[#CDEFD9] opacity-70 blur-2xl" aria-hidden />
          <img src="/og-image.png" alt="Wonder Clips turns a long video into short vertical clips" width={1200} height={630}
               className="w-full rounded-[28px] shadow-[0_30px_70px_-25px_rgba(87,58,252,.45)]" />
        </div>
      </section>

      {/* ---------- studio ---------- */}
      <section id="studio" className="mt-16 scroll-mt-24 lg:mt-24">
        <Reveal>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">Make your clips</h2>
              <p className="mt-1 text-zinc-600">Step 1: start the engine on your PC. Step 2: add a video. That is it.</p>
            </div>
          </div>
          <EngineGate><UploadCard /></EngineGate>
        </Reveal>
      </section>

      {/* ---------- how it works ---------- */}
      <section id="how" className="mt-16 scroll-mt-24 lg:mt-24">
        <Reveal><h2 className="text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">How it works</h2></Reveal>
        <ol className="mt-6 grid gap-4 md:grid-cols-3">
          {STEPS.map(({ Icon, title, body }, i) => (
            <li key={title}>
              <Reveal delay={i * 120} className="h-full">
                <div className="relative h-full rounded-3xl bg-[#F6F3FF] p-6 shadow-[0_10px_30px_-18px_rgba(87,58,252,.4)]">
                  <span className="absolute right-5 top-4 text-5xl font-extrabold text-[#D9CCFF]">{i + 1}</span>
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white text-[#573AFC] shadow-sm"><Icon width={26} height={26} /></span>
                  <div className="mt-4 text-lg font-bold text-zinc-900">{title}</div>
                  <p className="mt-1 text-[15px] leading-relaxed text-zinc-600">{body}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>

      {/* ---------- features ---------- */}
      <section className="mt-16 lg:mt-24">
        <Reveal><h2 className="text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">Everything you need</h2></Reveal>
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ Icon, tint, title, body }, i) => (
            <li key={title}>
              <Reveal delay={i * 90} className="h-full">
                <div className="h-full rounded-3xl bg-white p-5 shadow-[0_10px_34px_-18px_rgba(30,20,90,.35)] ring-1 ring-zinc-100">
                  <span className={`grid h-11 w-11 place-items-center rounded-2xl ${tint}`}><Icon width={22} height={22} /></span>
                  <div className="mt-3 font-bold text-zinc-900">{title}</div>
                  <p className="mt-1 text-sm leading-relaxed text-zinc-600">{body}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ul>
      </section>

      {/* ---------- quick answers ---------- */}
      <section className="mt-16 lg:mt-24">
        <Reveal><h2 className="text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">Quick answers</h2></Reveal>
        <div className="mt-6 grid gap-3 lg:max-w-3xl">
          {QUICK.map(({ q, a }) => (
            <details key={q} className="group rounded-2xl bg-[#F6F3FF] px-5 py-4">
              <summary className="cursor-pointer list-none font-semibold text-zinc-900 [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-3">{q}<span className="text-[#573AFC] transition group-open:rotate-45">+</span></span>
              </summary>
              <p className="mt-2 text-[15px] leading-relaxed text-zinc-700">{a}</p>
            </details>
          ))}
          <a href="/faq/" className="mt-1 font-semibold text-[#573AFC] hover:underline">See all questions →</a>
        </div>
      </section>

      {/* ---------- final call to action ---------- */}
      <Reveal className="mt-16 lg:mt-24">
        <section className="rounded-[32px] bg-gradient-to-br from-[#573AFC] to-[#8C6BFF] px-6 py-10 text-center text-white sm:px-12">
          <h2 className="text-2xl font-extrabold tracking-tight sm:text-4xl">Ready to make your first clip?</h2>
          <p className="mx-auto mt-2 max-w-xl text-white/85">Free, private and made by {SITE.author}. Set it up once and clip as many videos as you like.</p>
          <a href="#studio" className="mt-6 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3.5 font-semibold text-[#3E2A9E] transition hover:-translate-y-0.5">
            Start clipping <ArrowRightIcon width={18} height={18} />
          </a>
        </section>
      </Reveal>
    </div>
  );
}
