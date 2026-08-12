import type { ReactNode } from "react";

import { LocationProvider } from "./components/LocationContext";
import { GuidedProductTour } from "./components/GuidedProductTour";

export default function ProductLayout({ children }: { children: ReactNode }) {
  return (
    <LocationProvider>
      {children}
      <GuidedProductTour />
    </LocationProvider>
  );
}
