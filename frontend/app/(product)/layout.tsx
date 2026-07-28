import type { ReactNode } from "react";

import { LocationProvider } from "./components/LocationContext";

export default function ProductLayout({ children }: { children: ReactNode }) {
  return <LocationProvider>{children}</LocationProvider>;
}
