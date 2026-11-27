"use client";

import type { CaptionStyle, FontInfo } from "@/lib/api";

const PRESET_LABELS: Record<string, { name: string; desc: string }> = {
  bold: { name: "Bold creator", desc: "Big, uppercase, active word pops" },
  karaoke: { name: "Karaoke", desc: "Colour fills word by word" },
  minimal: { name: "Minimal", desc: "Clean subtitle on a soft box" },
  headline: { name: "Headline", desc: "Tall condensed, 2 words at a time" },
};

type Props = {
  style: CaptionStyle;
  presets: Record<string, CaptionStyle>;
  fonts: FontInfo[];
  onChange: (s: CaptionStyle) => void;
};

export function StylePanel({ style, presets, fonts, onChange }: Props) {
  const set = <K extends keyof CaptionStyle>(k: K, v: CaptionStyle[K]) => onChange({ ...style, [k]: v });
  const font = fonts.find((f) => f.family === style.font);

  return (
    <div className="space-y-6">
      <Section title="Style">
        <div className="grid grid-cols-2 gap-2">
          {Object.keys(presets).map((p) => (
            <button key={p} onClick={() => onChange({ ...presets[p] })}
                    className={`rounded-xl border p-3 text-left transition ${style.preset === p ? "border-violet-500 bg-violet-50 ring-1 ring-violet-500" : "border-zinc-200 hover:border-violet-300"}`}>
              <div className="text-sm font-semibold" style={{ fontFamily: `"${presets[p].font}"`, fontWeight: presets[p].bold ? 700 : 400 }}>
                {PRESET_LABELS[p]?.name ?? p}
              </div>
              <div className="mt-0.5 text-xs text-zinc-500">{PRESET_LABELS[p]?.desc}</div>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Font">
        <select value={style.font} onChange={(e) => {
                  const f = fonts.find((x) => x.family === e.target.value);
                  onChange({ ...style, font: e.target.value, bold: f?.has_bold ? style.bold : false });
                }}
                className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-[15px]"
                style={{ fontFamily: `"${style.font}"` }}>
          {fonts.map((f) => (
            <option key={f.family} value={f.family} style={{ fontFamily: `"${f.family}"` }}>
              {f.family} — {f.category}{f.devanagari ? " · हिंदी" : ""}
            </option>
          ))}
        </select>
        <div className="mt-3 flex gap-2">
          <Seg active={!style.bold} onClick={() => set("bold", false)}>Regular</Seg>
          <Seg active={style.bold} disabled={!font?.has_bold} onClick={() => set("bold", true)}
               title={font?.has_bold ? undefined : "This font has a single weight"}>Bold</Seg>
          <Seg active={style.uppercase} onClick={() => set("uppercase", !style.uppercase)}>AA Uppercase</Seg>
        </div>
        <Slider label="Size" value={style.size} min={30} max={160} onChange={(v) => set("size", v)} />
        <Slider label="Words per line" value={style.max_words} min={1} max={8} onChange={(v) => set("max_words", v)} />
      </Section>

      <Section title="Animation">
        <div className="flex gap-2">
          <Seg active={style.animation === "highlight"} onClick={() => set("animation", "highlight")}>Word highlight</Seg>
          <Seg active={style.animation === "karaoke"} onClick={() => set("animation", "karaoke")}>Karaoke</Seg>
          <Seg active={style.animation === "none"} onClick={() => set("animation", "none")}>None</Seg>
        </div>
        {style.animation === "highlight" && (
          <Slider label="Pop size" value={style.highlight_scale} min={100} max={140} unit="%" onChange={(v) => set("highlight_scale", v)} />
        )}
      </Section>

      <Section title="Colours">
        <div className="grid grid-cols-3 gap-3">
          <Color label="Text" value={style.text_color} onChange={(v) => set("text_color", v)} />
          <Color label="Highlight" value={style.highlight_color} onChange={(v) => set("highlight_color", v)} />
          <Color label="Outline" value={style.outline_color} onChange={(v) => set("outline_color", v)} />
        </div>
        <Slider label="Outline" value={style.outline} min={0} max={12} onChange={(v) => set("outline", v)} />
        <Slider label="Shadow" value={style.shadow} min={0} max={8} onChange={(v) => set("shadow", v)} />
      </Section>

      <Section title="Background">
        <div className="flex gap-2">
          <Seg active={!style.box} onClick={() => set("box", false)}>None</Seg>
          <Seg active={style.box} onClick={() => set("box", true)}>Box</Seg>
        </div>
        {style.box && (
          <div className="mt-3 grid grid-cols-[auto_1fr] items-end gap-3">
            <Color label="Box" value={style.box_color} onChange={(v) => set("box_color", v)} />
            <Slider label="Opacity" value={Math.round(style.box_opacity * 100)} min={0} max={100} unit="%"
                    onChange={(v) => set("box_opacity", v / 100)} />
          </div>
        )}
      </Section>

      <Section title="Position">
        <div className="flex gap-2">
          {(["upper", "middle", "lower"] as const).map((p) => (
            <Seg key={p} active={style.position === p} onClick={() => set("position", p)}>
              {p === "upper" ? "Top" : p === "middle" ? "Middle" : "Bottom"}
            </Seg>
          ))}
        </div>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
      {children}
    </section>
  );
}

function Seg({ active, disabled, onClick, children, title }: {
  active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode; title?: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
            className={`flex-1 rounded-lg border px-2.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${active ? "border-violet-500 bg-violet-50 text-violet-800" : "border-zinc-200 text-zinc-600 hover:border-violet-300"}`}>
      {children}
    </button>
  );
}

function Slider({ label, value, min, max, unit = "", onChange }: {
  label: string; value: number; min: number; max: number; unit?: string; onChange: (v: number) => void;
}) {
  return (
    <label className="mt-3 block">
      <span className="flex justify-between text-sm text-zinc-600">
        <span>{label}</span><span className="tabular-nums text-zinc-400">{value}{unit}</span>
      </span>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(+e.target.value)}
             className="mt-1 w-full accent-violet-600" />
    </label>
  );
}

function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block text-sm text-zinc-600">
      {label}
      <span className="mt-1 flex items-center gap-2 rounded-lg border border-zinc-200 p-1.5">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())}
               className="h-7 w-9 cursor-pointer rounded border-0 bg-transparent p-0" />
        <span className="font-mono text-xs text-zinc-500">{value}</span>
      </span>
    </label>
  );
}
