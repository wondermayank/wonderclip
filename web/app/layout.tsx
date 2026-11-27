import type { Metadata, Viewport } from "next";
import { Shell } from "@/components/Shell";
import { Intro } from "@/components/Intro";
import { FOOTER_HTML, HEADER_HTML } from "@/lib/shellHtml";
import { SITE } from "@/lib/site";
import "./globals.css";
import "./shell.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: "Wonder Clips — Turn long videos into viral clips", template: "%s · Wonder Clips" },
  description: "Free AI video clipper that runs on your own computer. Paste a link or upload a video and get captioned, vertical, ready-to-post clips.",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "Wonder Clips — Turn long videos into viral clips",
    description: "Free AI video clipper that runs on your own computer. No uploads, no sign-up, no watermark.",
    url: SITE.url, siteName: "Wonder Clips", images: ["/og-image.png"], type: "website",
  },
  twitter: { card: "summary_large_image", images: ["/og-image.png"] },
};
export const viewport: Viewport = { themeColor: "#573AFC" };

const BOOT = `(function(){try{var d=document.documentElement,t=localStorage.getItem("theme");d.setAttribute("data-theme",t==="dark"?"dark":"light");if(sessionStorage.getItem("wc-intro"))d.classList.add("seen-intro")}catch(e){document.documentElement.setAttribute("data-theme","light")}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" />
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body className="bg-white text-zinc-900">
        <Intro />
        <div id="wc-head" dangerouslySetInnerHTML={{ __html: HEADER_HTML }} />
        <main>{children}</main>
        <div id="wc-foot" dangerouslySetInnerHTML={{ __html: FOOTER_HTML }} />
        <Shell />
      </body>
    </html>
  );
}
