"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { CaptionStyle, EditorData, EditorWord } from "@/lib/api";
import { mediaUrl } from "@/lib/api";
import { cleanText, cropXAt, hexToRgba, timedPages, wordsInRange } from "@/lib/captions";

export type PreviewHandle = { seek: (t: number) => void; play: () => void; currentTime: () => number };

type Props = {
  data: EditorData;
  start: number;
  end: number;
  style: CaptionStyle;
  words: EditorWord[];
  renderedStart: number; // clip start the saved crop path belongs to
  width?: number;
  onTime?: (t: number) => void;
};

/**
 * Live preview: plays the ORIGINAL video inside a 9:16 frame and draws captions in HTML,
 * so every change shows instantly. The saved render (FFmpeg + libass) is the exact output.
 */
export const Preview = forwardRef<PreviewHandle, Props>(function Preview(
  { data, start, end, style, words, renderedStart, width = 340, onTime }, ref,
) {
  const height = Math.round((width * 16) / 9);
  const k = height / data.limits.output_height; // caption px scale vs 1080x1920
  const video = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(start);
  const [playing, setPlaying] = useState(false);

  useImperativeHandle(ref, () => ({
    seek: (s) => { if (video.current) video.current.currentTime = s; setT(s); },
    play: () => { video.current?.play(); },
    currentTime: () => video.current?.currentTime ?? start,
  }), [start]);

  // Keep playback inside [start, end): loop back to the start.
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const v = video.current;
      if (v) {
        if (v.currentTime >= end || v.currentTime < start - 0.25) {
          v.currentTime = start;
          if (v.currentTime >= end) v.pause();
        }
        setT(v.currentTime);
        onTime?.(v.currentTime);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, end, onTime]);

  useEffect(() => {
    const v = video.current;
    if (v && (v.currentTime < start || v.currentTime > end)) v.currentTime = start;
  }, [start, end]);

  const pages = useMemo(() => timedPages(wordsInRange(words, start, end), style, end), [words, start, end, style]);
  const page = pages.find((p) => t >= p.start && t < p.end);

  // ----- framing (mirrors the render's layout) -----
  const { reframe: rf, source } = data;
  let videoStyle: React.CSSProperties;
  if (rf.layout === "track") {
    const scale = height / source.height;
    const cropW = rf.crop_w || Math.round((source.height * 9) / 16);
    // Clips rendered before crop paths were saved: centre until the next render saves a path.
    const x = rf.samples.length ? cropXAt(rf.samples, t - renderedStart) : (source.width - cropW) / 2;
    videoStyle = { position: "absolute", top: 0, left: -x * scale, height, width: source.width * scale, maxWidth: "none" };
  } else if (rf.layout === "native") {
    videoStyle = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" };
  } else {
    videoStyle = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" };
  }

  // ----- caption styling (same numbers as the ASS style) -----
  const fontSize = style.size * k;
  const stroke = style.box ? 0 : style.outline * k * 2;
  const captionBox: React.CSSProperties = {
    position: "absolute", left: 90 * k, right: 90 * k, textAlign: "center",
    fontFamily: `"${style.font}", sans-serif`, fontWeight: style.bold ? 700 : 400, fontSize, lineHeight: 1.2,
    color: style.text_color,
    ...(style.position === "lower" ? { bottom: 0.24 * height } : style.position === "upper" ? { top: 0.14 * height } : { top: "50%", transform: "translateY(-50%)" }),
  };
  const textStyle: React.CSSProperties = {
    WebkitTextStroke: stroke ? `${stroke}px ${style.outline_color}` : undefined,
    paintOrder: "stroke fill",
    textShadow: style.shadow ? `${style.shadow * k * 1.5}px ${style.shadow * k * 1.5}px 0 rgba(0,0,0,.6)` : undefined,
    ...(style.box ? { background: hexToRgba(style.box_color, style.box_opacity), padding: `${8 * k}px ${18 * k}px`,
      boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone", borderRadius: 4 } : {}),
  };

  const togglePlay = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) { if (v.currentTime >= end || v.currentTime < start) v.currentTime = start; v.play(); } else v.pause();
  };

  return (
    <div className="select-none">
      <div className="relative overflow-hidden rounded-2xl bg-zinc-950 shadow-lg" style={{ width, height }} onClick={togglePlay}>
        {rf.layout === "fit" && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={mediaUrl(data.clip.thumbnail_url)} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover blur-xl brightness-75" />
        )}
        <video
          ref={video}
          src={mediaUrl(source.video_url)}
          preload="auto"
          playsInline
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          style={videoStyle}
        />
        {page && (
          <div style={captionBox}>
            <span style={textStyle}>
              {page.words.map((w, i) => {
                const text = cleanText(w.text, style);
                const active = t >= w.start && (i + 1 < page.words.length ? t < page.words[i + 1].start : true);
                let wordStyle: React.CSSProperties = {};
                if (style.animation === "highlight" && active) {
                  wordStyle = { color: style.highlight_color, display: "inline-block",
                    transform: `scale(${style.highlight_scale / 100})`, margin: `0 ${fontSize * (style.highlight_scale - 100) / 200}px` };
                } else if (style.animation === "karaoke") {
                  const p = Math.min(1, Math.max(0, (t - w.start) / Math.max(w.end - w.start, 0.01)));
                  wordStyle = p >= 1 ? { color: style.highlight_color } : p > 0 ? {
                    backgroundImage: `linear-gradient(90deg, ${style.highlight_color} ${p * 100}%, ${style.text_color} ${p * 100}%)`,
                    WebkitBackgroundClip: "text", color: "transparent" } : {};
                }
                return <span key={w.i}>{i > 0 && " "}<span style={wordStyle}>{text}</span></span>;
              })}
            </span>
          </div>
        )}
        {!playing && (
          <div className="absolute inset-0 grid place-items-center bg-black/10">
            <span className="grid h-14 w-14 place-items-center rounded-full bg-white/90 text-violet-700 shadow-lg">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            </span>
          </div>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-zinc-400">Live preview · the saved render is pixel-exact</p>
    </div>
  );
});
