import type { Metadata } from "next";
import { InfoPage, Section, A } from "@/components/InfoPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "FAQ",
  description: "How to install Wonder Clips, what it needs and how your videos stay private.",
};

type QA = { q: string; a: React.ReactNode; open?: boolean };

const GROUPS: { title: string; items: QA[] }[] = [
  {
    title: "Safety & privacy",
    items: [
      { q: "Is Wonder Clips safe to use?", open: true, a: <>Yes. The website is a static page and the AI work is done by a small engine you install on your own Windows PC. The engine only listens on <code>127.0.0.1</code> (your own computer) and only accepts requests from {SITE.url.replace("https://", "")}. The full source is public on <A href={SITE.repo}>GitHub</A>.</> },
      { q: "Does Wonder Clips upload my videos anywhere?", a: <>No. Transcription, highlight finding, face tracking, captions and rendering all run on your computer. Videos and clips are deleted automatically after {SITE.retentionHours} hours. There are no accounts, no analytics and no tracking.</> },
      { q: "Why does Windows say “Windows protected your PC”?", a: <>Windows shows this for programs that are not code-signed. Code signing is a paid certificate that many small free projects do not have. Click <b>More info</b>, then <b>Run anyway</b>. You can also read the installer script first on GitHub.</> },
      { q: "My browser asks to let this site “access apps on this device”. Should I allow it?", a: <>Yes. That is how this page talks to the engine on your computer. It does not give the site access to your files or camera. If you blocked it by mistake, click the icon at the left of the address bar, set <b>Local network access</b> to <b>Allow</b> and reload.</> },
    ],
  },
  {
    title: "Using Wonder Clips",
    items: [
      { q: "Is it free?", a: <>Yes. No subscription, no limits and no watermark. It uses free open-source AI models that run on your own hardware.</> },
      { q: "What do I need to run it?", a: <>Windows 10 or 11 (64-bit), about 8 GB of free disk space and an internet connection for the one-time setup. An NVIDIA graphics card with 6 GB or more memory is recommended. Without one it still works on the processor, just slower.</> },
      { q: "How do I install it?", a: <>On the home page, press <b>Download installer</b> and double-click <b>Install-WonderClips.bat</b>. Setup takes about 5 to 15 minutes. Afterwards use the <b>Wonder Clips</b> icon on your Desktop to start the engine and open the site.</> },
      { q: "How long can the video be?", a: <>Up to 30 minutes. Wonder Clips finds the best moments and makes up to 8 clips with captions, reframed to 9:16.</> },
      { q: "Can I paste a YouTube or Instagram link?", a: <>Yes. Your computer downloads the video directly from that platform. Only use videos you have the right to use.</> },
      { q: "The page says the engine is not running.", a: <>Start the engine from the <b>Wonder Clips</b> icon on your Desktop, allow Local network access in your browser and reload this page.</> },
      { q: "How do I remove it?", a: <>Delete the folder <code>%LOCALAPPDATA%\WonderClip</code> and the Wonder Clips shortcuts on your Desktop and Start menu.</> },
    ],
  },
  {
    title: "About",
    items: [
      { q: "Who made Wonder Clips?", a: <>Wonder Clips is made by {SITE.author} (wondermayank) and is open source. Want your own copy? The README on <A href={SITE.repo}>GitHub</A> explains how to set one up.</> },
      { q: "How do I contact you?", a: <>Use <A href={SITE.contact}>wondermayank.in/contact</A> or <A href={SITE.issues}>open an issue on GitHub</A>.</> },
    ],
  },
];

export default function FaqPage() {
  return (
    <InfoPage title="Frequently asked questions" showUpdated={false}
      intro="Everything about installing Wonder Clips, keeping your videos private and getting great clips.">
      {GROUPS.map((g) => (
        <Section key={g.title} title={g.title}>
          {g.items.map((it) => (
            <details key={it.q} open={it.open} className="group rounded-2xl bg-[#F6F3FF] px-5 py-4">
              <summary className="cursor-pointer list-none font-semibold text-zinc-900 [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-3">{it.q}<span className="text-[#573AFC] transition group-open:rotate-45">+</span></span>
              </summary>
              <div className="mt-2 text-[15px] leading-relaxed text-zinc-700">{it.a}</div>
            </details>
          ))}
        </Section>
      ))}
    </InfoPage>
  );
}
