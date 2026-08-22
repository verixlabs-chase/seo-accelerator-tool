import type { ReactNode } from "react";

export type ProductIconName =
  | "overview"
  | "rankings"
  | "keyword-research"
  | "local-search"
  | "website-health"
  | "next-steps"
  | "reports"
  | "connections"
  | "locations"
  | "search-value"
  | "ai-search"
  | "competitors"
  | "content"
  | "listings"
  | "reviews"
  | "profile-campaigns"
  | "client-access"
  | "activity"
  | "notifications"
  | "help"
  | "chart"
  | "calendar"
  | "check"
  | "warning"
  | "arrow-up"
  | "arrow-down"
  | "no-change"
  | "empty"
  | "info"
  | "spark";

type ProductIconProps = {
  name: ProductIconName;
  size?: number;
  className?: string;
  label?: string;
};

const commonPathProps = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function iconPaths(name: ProductIconName): ReactNode {
  switch (name) {
    case "overview":
      return (
        <>
          <rect x="3" y="3" width="7" height="7" rx="1.5" {...commonPathProps} />
          <rect x="14" y="3" width="7" height="4" rx="1.5" {...commonPathProps} />
          <rect x="14" y="11" width="7" height="10" rx="1.5" {...commonPathProps} />
          <rect x="3" y="14" width="7" height="7" rx="1.5" {...commonPathProps} />
        </>
      );
    case "rankings":
      return (
        <>
          <path d="M4 20V13M10 20V9M16 20V5" {...commonPathProps} />
          <path d="m14 5 2-2 2 2M16 3v8" {...commonPathProps} />
          <path d="M3 20h18" {...commonPathProps} />
        </>
      );
    case "keyword-research":
      return (
        <>
          <circle cx="10.5" cy="10.5" r="6.5" {...commonPathProps} />
          <path d="m15.5 15.5 5 5" {...commonPathProps} />
          <path d="m10.5 6 .8 2.7 2.7.8-2.7.8-.8 2.7-.8-2.7L8 9.5l2.7-.8z" {...commonPathProps} />
        </>
      );
    case "local-search":
      return (
        <>
          <path d="M12 21s6-5.3 6-11a6 6 0 1 0-12 0c0 5.7 6 11 6 11Z" {...commonPathProps} />
          <circle cx="12" cy="10" r="2.2" {...commonPathProps} />
          <path d="M3.5 20.5h4M16.5 20.5h4" {...commonPathProps} />
        </>
      );
    case "website-health":
      return (
        <>
          <path d="M4 6.5h16v12H4z" {...commonPathProps} />
          <path d="M4 9.5h16M7 6.5V4h10v2.5" {...commonPathProps} />
          <path d="m7 14 2.2-2 2.1 4 2.2-5 1.8 3H18" {...commonPathProps} />
        </>
      );
    case "next-steps":
      return (
        <>
          <rect x="4" y="3" width="16" height="18" rx="2" {...commonPathProps} />
          <path d="m7 8 1.3 1.3L10.8 7M13 8h4M7 14l1.3 1.3 2.5-2.3M13 14h4" {...commonPathProps} />
        </>
      );
    case "reports":
      return (
        <>
          <path d="M6 3h9l4 4v14H6z" {...commonPathProps} />
          <path d="M15 3v5h4M9 17v-3M12.5 17v-6M16 17v-4" {...commonPathProps} />
        </>
      );
    case "connections":
      return (
        <>
          <path d="M8 8 5 5M16 16l3 3M6.5 11.5l5-5a3.5 3.5 0 0 1 5 5l-1 1M17.5 12.5l-5 5a3.5 3.5 0 0 1-5-5l1-1" {...commonPathProps} />
        </>
      );
    case "locations":
      return (
        <>
          <path d="M4 21V8l6-3v16M10 21V3l10 4v14M2 21h20" {...commonPathProps} />
          <path d="M7 10h1M7 14h1M14 9h2M14 13h2M14 17h2" {...commonPathProps} />
        </>
      );
    case "search-value":
      return (
        <>
          <circle cx="9" cy="10" r="5" {...commonPathProps} />
          <path d="M9 7v6M7.5 8h2.2a1.3 1.3 0 0 1 0 2.6H8.3a1.3 1.3 0 0 0 0 2.6h2.2M14 17h7M18 13l3 4-3 4" {...commonPathProps} />
        </>
      );
    case "ai-search":
      return (
        <>
          <path d="M4 4h16v11H9l-5 4z" {...commonPathProps} />
          <path d="m14.5 6.5.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7z" {...commonPathProps} />
          <path d="M7.5 8.5h3M7.5 11.5h4.5" {...commonPathProps} />
        </>
      );
    case "competitors":
      return (
        <>
          <circle cx="8" cy="8" r="3" {...commonPathProps} />
          <circle cx="17" cy="9" r="2.5" {...commonPathProps} />
          <path d="M3 20a5 5 0 0 1 10 0M13 19a4 4 0 0 1 8 0" {...commonPathProps} />
        </>
      );
    case "content":
      return (
        <>
          <path d="M6 3h9l4 4v14H6z" {...commonPathProps} />
          <path d="M15 3v5h4M9 12h7M9 16h5" {...commonPathProps} />
          <path d="m14.5 19 5-5 1.5 1.5-5 5-2 .5z" {...commonPathProps} />
        </>
      );
    case "listings":
      return (
        <>
          <rect x="3" y="4" width="18" height="16" rx="2" {...commonPathProps} />
          <path d="M3 9h18M8 9v11M12 13h5M12 16h3" {...commonPathProps} />
          <circle cx="5.5" cy="6.5" r=".5" fill="currentColor" />
        </>
      );
    case "reviews":
      return (
        <>
          <path d="M4 4h16v12H9l-5 4z" {...commonPathProps} />
          <path d="m12 7 .8 1.7 1.9.2-1.4 1.3.4 1.9-1.7-.9-1.7.9.4-1.9-1.4-1.3 1.9-.2z" {...commonPathProps} />
        </>
      );
    case "profile-campaigns":
      return (
        <>
          <path d="M4 13V9l10-4v12L4 13Z" {...commonPathProps} />
          <path d="M14 8.5h2.5a3.5 3.5 0 0 1 0 7H14M6 13l1 7h3l-1-6" {...commonPathProps} />
          <path d="M19 5.5 21 4M19.5 19l2 1.5" {...commonPathProps} />
        </>
      );
    case "client-access":
      return (
        <>
          <rect x="3" y="4" width="18" height="16" rx="2" {...commonPathProps} />
          <circle cx="9" cy="10" r="2.4" {...commonPathProps} />
          <path d="M5.5 17a3.5 3.5 0 0 1 7 0M15 9h3M15 13h3" {...commonPathProps} />
        </>
      );
    case "activity":
      return (
        <>
          <path d="M6 4v16" {...commonPathProps} />
          <circle cx="6" cy="7" r="2" fill="#0f1012" stroke="currentColor" strokeWidth="1.7" />
          <circle cx="6" cy="13" r="2" fill="#0f1012" stroke="currentColor" strokeWidth="1.7" />
          <circle cx="6" cy="19" r="2" fill="#0f1012" stroke="currentColor" strokeWidth="1.7" />
          <path d="M10 7h9M10 13h6M10 19h8" {...commonPathProps} />
        </>
      );
    case "notifications":
      return (
        <>
          <path d="M6.5 9.5a5.5 5.5 0 0 1 11 0c0 6 2.5 6.5 2.5 6.5H4s2.5-.5 2.5-6.5Z" {...commonPathProps} />
          <path d="M9.5 19a2.7 2.7 0 0 0 5 0" {...commonPathProps} />
          <path d="M12 2v2" {...commonPathProps} />
        </>
      );
    case "help":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...commonPathProps} />
          <path d="M9.6 9a2.6 2.6 0 1 1 4.7 1.55c-.8 1.05-2.3 1.35-2.3 3.05" {...commonPathProps} />
          <path d="M12 17.5h.01" {...commonPathProps} />
        </>
      );
    case "chart":
      return (
        <>
          <path d="M4 20V4M4 20h16" {...commonPathProps} />
          <path d="m7 16 4-5 3 2 5-7" {...commonPathProps} />
          <circle cx="7" cy="16" r="1" fill="currentColor" />
          <circle cx="11" cy="11" r="1" fill="currentColor" />
          <circle cx="14" cy="13" r="1" fill="currentColor" />
          <circle cx="19" cy="6" r="1" fill="currentColor" />
        </>
      );
    case "calendar":
      return (
        <>
          <rect x="3" y="5" width="18" height="16" rx="2" {...commonPathProps} />
          <path d="M8 3v4M16 3v4M3 10h18M8 14h3M8 17h6" {...commonPathProps} />
        </>
      );
    case "check":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...commonPathProps} />
          <path d="m8 12 2.5 2.5L16.5 9" {...commonPathProps} />
        </>
      );
    case "warning":
      return (
        <>
          <path d="m12 3 9 17H3z" {...commonPathProps} />
          <path d="M12 9v5M12 17h.01" {...commonPathProps} />
        </>
      );
    case "arrow-up":
      return <path d="M12 20V5M6 11l6-6 6 6" {...commonPathProps} />;
    case "arrow-down":
      return <path d="M12 4v15M6 13l6 6 6-6" {...commonPathProps} />;
    case "no-change":
      return <path d="M5 12h14M15 8l4 4-4 4" {...commonPathProps} />;
    case "empty":
      return (
        <>
          <circle cx="11" cy="11" r="7" {...commonPathProps} />
          <path d="m16 16 5 5M8 11h6" {...commonPathProps} />
        </>
      );
    case "info":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...commonPathProps} />
          <path d="M12 11v6M12 7h.01" {...commonPathProps} />
        </>
      );
    case "spark":
      return (
        <>
          <path d="m12 3 1.4 5.6L19 10l-5.6 1.4L12 17l-1.4-5.6L5 10l5.6-1.4z" {...commonPathProps} />
          <path d="m19 16 .6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6z" {...commonPathProps} />
        </>
      );
  }
}

export function ProductIcon({
  name,
  size = 20,
  className = "",
  label,
}: ProductIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {label ? <title>{label}</title> : null}
      {iconPaths(name)}
    </svg>
  );
}
