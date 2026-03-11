export const colorTokens = {
  background: "#070b16",
  surface1: "rgba(11, 18, 32, 0.88)",
  surface2: "rgba(18, 26, 46, 0.92)",
  surface3: "rgba(28, 36, 66, 0.96)",
  border: "rgba(148, 163, 184, 0.16)",
  borderStrong: "rgba(129, 140, 248, 0.28)",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  textSoft: "#94a3b8",
  indigo: "#6366f1",
  violet: "#8b5cf6",
  blue: "#38bdf8",
  green: "#22c55e",
  yellow: "#facc15",
  red: "#f87171",
} as const;

export const typographyScale = {
  display: "text-4xl font-semibold tracking-[-0.03em] md:text-5xl",
  heroMetric: "text-3xl font-semibold tracking-[-0.04em] md:text-4xl",
  metric: "text-2xl font-semibold tracking-[-0.03em]",
  title: "text-lg font-semibold tracking-[-0.02em]",
  section: "text-sm font-semibold uppercase tracking-[0.16em] text-slate-400",
  body: "text-sm leading-6 text-slate-300",
  caption: "text-xs leading-5 text-slate-400",
} as const;

export const spacingScale = {
  pageX: "px-4 md:px-6 xl:px-8",
  pageY: "py-4 md:py-6",
  sectionGap: "gap-6",
  gridGap: "gap-5",
  cardPadding: "p-5 md:p-6",
} as const;

export const surfaceStyles = {
  app:
    "min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(99,102,241,0.18),transparent_26%),radial-gradient(circle_at_top_right,rgba(139,92,246,0.14),transparent_24%),linear-gradient(180deg,#050816_0%,#070b16_36%,#090d18_100%)] text-slate-50",
  shell: "rounded-[28px] border border-white/10 bg-slate-950/55 shadow-[0_24px_80px_rgba(15,23,42,0.42)] backdrop-blur-xl",
  card: "rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.72))] shadow-[0_18px_55px_rgba(15,23,42,0.36)] backdrop-blur-xl",
  cardElevated:
    "rounded-[24px] border border-indigo-400/20 bg-[linear-gradient(180deg,rgba(27,37,72,0.96),rgba(17,24,39,0.88))] shadow-[0_0_0_1px_rgba(99,102,241,0.16),0_18px_50px_rgba(99,102,241,0.12)]",
  cardSubtle: "rounded-[20px] border border-white/10 bg-slate-950/45",
  sidebar: "border-r border-white/10 bg-slate-950/50 backdrop-blur-xl",
  topBar: "border-b border-white/10 bg-slate-950/45 backdrop-blur-xl",
  trustStrip: "border-b border-indigo-400/12 bg-indigo-500/6",
} as const;

export const cardStyles = {
  base: `${surfaceStyles.card} ${spacingScale.cardPadding}`,
  elevated: `${surfaceStyles.cardElevated} ${spacingScale.cardPadding}`,
  compact: `${surfaceStyles.card} p-4`,
} as const;

export const tailwindPatterns = {
  kpiValue: "text-3xl font-semibold tracking-[-0.04em] text-white",
  subtleLabel: "text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400",
  insightText: "text-sm leading-6 text-slate-300",
  actionButton:
    "inline-flex items-center justify-center rounded-full border border-indigo-400/25 bg-indigo-500/12 px-4 py-2 text-sm font-medium text-indigo-100 transition hover:border-indigo-300/35 hover:bg-indigo-500/18",
  secondaryButton:
    "inline-flex items-center justify-center rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-white/10",
} as const;

export const chartPalette = {
  primary: "#818cf8",
  secondary: "#a78bfa",
  info: "#38bdf8",
  success: "#22c55e",
  warning: "#facc15",
  danger: "#f87171",
  muted: "#64748b",
} as const;
