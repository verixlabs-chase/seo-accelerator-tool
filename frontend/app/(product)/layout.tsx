import type { ReactNode } from "react";

import { LocationProvider } from "./components/LocationContext";
import { GuidedProductTour } from "./components/GuidedProductTour";
import { ProductRoleGuard } from "./components/ProductRoleGuard";

export default function ProductLayout({ children }: { children: ReactNode }) {
  return (
    <ProductRoleGuard>
      <LocationProvider>
        {children}
        <GuidedProductTour />
      </LocationProvider>
    </ProductRoleGuard>
  );
}
