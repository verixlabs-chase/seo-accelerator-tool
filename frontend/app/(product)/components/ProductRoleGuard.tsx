"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { platformApi } from "../../platform/api";

export function ProductRoleGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let active = true;
    void platformApi("/auth/me", { method: "GET" })
      .then((user) => {
        if (!active) return;
        if (user?.org_role === "org_client") {
          router.replace("/client-reports");
          return;
        }
        setAllowed(true);
      })
      .catch(() => {
        if (active) router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!allowed) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#0d0e10] text-zinc-300" role="status">
        Opening your workspace...
      </main>
    );
  }
  return children;
}
