export const colorTokens = {
  background: "#0b0b0c",
  surface1: "#111214",
  surface2: "#141518",
  surface3: "#1a1b1f",
  border: "#26272c",
  borderStrong: "rgba(255, 106, 26, 0.45)",
  text: "#f5f5f5",
  textMuted: "#d0d0d0",
  textSoft: "#878787",
  indigo: "#ff6a1a",
  violet: "#ff7f3f",
  blue: "#ff944f",
  green: "#22c55e",
  yellow: "#f59e0b",
  red: "#f87171",
} as const;

export const typographyScale = {
  display: "text-4xl font-bold tracking-[-0.05em] md:text-[2.85rem]",
  heroMetric: "text-[2rem] font-semibold tracking-[-0.04em] md:text-[2.35rem]",
  metric: "text-[1.75rem] font-semibold tracking-[-0.03em]",
  title: "text-base font-semibold tracking-[-0.02em]",
  section: "text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500",
  body: "text-sm font-normal leading-5 text-zinc-300",
  caption: "text-xs leading-5 text-zinc-500",
} as const;

export const spacingScale = {
  pageX: "px-4 md:px-5 xl:px-6",
  pageY: "py-3 md:py-4",
  sectionGap: "gap-4",
  gridGap: "gap-4",
  cardPadding: "p-4",
} as const;

export const surfaceStyles = {
  app:
    "min-h-screen bg-[radial-gradient(circle_at_22%_0%,rgba(255,106,26,0.12),transparent_16%),radial-gradient(circle_at_70%_12%,rgba(255,255,255,0.035),transparent_22%),linear-gradient(180deg,#09090a_0%,#0b0b0c_48%,#101114_100%)] text-zinc-50",
  shell: "rounded-md border border-[#26272c] bg-[#0f1012] shadow-[0_0_30px_rgba(0,0,0,0.4)]",
  card: "rounded-md border border-[#26272c] bg-[#141518] shadow-[0_0_30px_rgba(0,0,0,0.4)]",
  cardElevated:
    "rounded-md border border-[#3a2a20] bg-[#161417] shadow-[0_0_30px_rgba(0,0,0,0.4)]",
  cardSubtle: "rounded-md border border-[#26272c] bg-[#111214]",
  sidebar: "border-r border-[#26272c] bg-[#0b0b0c]",
  topBar: "border-b border-[#26272c] bg-[#101114]",
  trustStrip: "border-b border-[#26272c] bg-[#111214]",
} as const;

export const cardStyles = {
  base: `${surfaceStyles.card} ${spacingScale.cardPadding}`,
  elevated: `${surfaceStyles.cardElevated} ${spacingScale.cardPadding}`,
  compact: `${surfaceStyles.card} p-3.5`,
} as const;

export const tailwindPatterns = {
  kpiValue: "text-[2rem] font-semibold tracking-[-0.04em] text-white",
  subtleLabel: "text-[11px] font-medium uppercase tracking-[0.18em] text-zinc-500",
  insightText: "text-sm leading-5 text-zinc-300",
  actionButton:
    "inline-flex items-center justify-center rounded-md border border-accent-500/35 bg-accent-500/10 px-3 py-1.5 text-sm font-medium text-zinc-100 transition hover:border-accent-500/55 hover:bg-accent-500/18",
  secondaryButton:
    "inline-flex items-center justify-center rounded-md border border-[#26272c] bg-[#141518] px-3 py-1.5 text-sm font-medium text-zinc-200 transition hover:bg-[#1a1b1f]",
} as const;

export const chartPalette = {
  primary: "#ff6a1a",
  secondary: "#ff7f3f",
  info: "#ff944f",
  success: "#22c55e",
  warning: "#f59e0b",
  danger: "#f87171",
  muted: "#52525b",
} as const;
