import type { ReactNode } from "react";

import { LocationProvider } from "../(product)/components/LocationContext";

export default function LegacyAppLayout({ children }: { children: ReactNode }) {
  return <LocationProvider>{children}</LocationProvider>;
}
