import { expect, test, type Page } from "@playwright/test";


async function closeTourIfShown(page: Page) {
  const tour = page.getByRole("dialog");
  if (await tour.isVisible().catch(() => false)) {
    await tour.getByRole("button", { name: "Close" }).click();
  }
}


async function signInAsSmokeOwner(page: Page) {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  const workspaceName = process.env.E2E_WORKSPACE_NAME;
  test.skip(
    !email || !password,
    "Set E2E_EMAIL and E2E_PASSWORD to run the authenticated production journey.",
  );

  await page.goto("/login");
  await page.getByLabel("Email").fill(email || "");
  await page.getByLabel("Password").fill(password || "");
  await page.getByRole("button", { name: "Sign in" }).click();

  const workspacePrompt = page.getByText(
    "Choose the business you want to open",
    { exact: true },
  );
  await expect
    .poll(async () => {
      if (/\/dashboard(?:\?|$)/.test(page.url())) return "dashboard";
      if (await workspacePrompt.isVisible().catch(() => false)) return "workspace";
      return "waiting";
    }, { timeout: 30_000 })
    .not.toBe("waiting");

  if (await workspacePrompt.isVisible().catch(() => false)) {
    if (!workspaceName) {
      throw new Error(
        "Set E2E_WORKSPACE_NAME to the exact dedicated smoke workspace name.",
      );
    }
    const workspaceChoice = page
      .getByRole("button")
      .filter({ hasText: workspaceName })
      .filter({ hasText: "Open" });
    await expect(workspaceChoice).toHaveCount(1);
    await workspaceChoice.click();
  }

  await page.waitForURL(/\/dashboard(?:\?|$)/);
  await expect(
    page.getByRole("heading", { name: "What matters for your business today" }),
  ).toBeVisible();
  await closeTourIfShown(page);
}


test("public sign-in remains understandable and accessible", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveAttribute("autocomplete", "email");
  await expect(page.getByLabel("Password")).toHaveAttribute("autocomplete", "current-password");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
});


test("owner can read the critical journey on desktop and mobile without changing data", async ({ page }) => {
  const browserProblemTypes: string[] = [];
  let logoutUrl = "";
  page.on("console", (message) => {
    if (message.type() === "warning" || message.type() === "error") {
      browserProblemTypes.push(message.type());
    }
  });
  page.on("pageerror", () => browserProblemTypes.push("pageerror"));
  page.on("response", (response) => {
    if (
      response.request().method() === "POST" &&
      /\/auth\/(?:login|select-org)(?:\?|$)/.test(response.url())
    ) {
      logoutUrl = response.url().replace(/\/auth\/(?:login|select-org)(?:\?.*)?$/, "/auth/logout");
    }
  });

  try {
    await signInAsSmokeOwner(page);
    if (!logoutUrl) {
      throw new Error("The smoke login response did not provide a revocable session endpoint.");
    }

    const locationChoice = page.getByLabel(
      "Choose the location shown across the workspace",
    );
    await expect(locationChoice).toBeVisible();
    await expect(locationChoice).toBeEnabled();
    await expect(locationChoice).toHaveValue(/\S+/);
    expect(await locationChoice.locator("option").count()).toBeGreaterThanOrEqual(2);

    const desktopNavigation = page.getByRole("navigation", { name: "Product navigation" });
    await expect(desktopNavigation).toBeVisible();
    await desktopNavigation.getByRole("link", { name: "Reports", exact: true }).click();
    await expect(page).toHaveURL(/\/reports(?:\?|$)/);
    await expect(
      page.getByRole("heading", { name: "Create a clear update you can share" }),
    ).toBeVisible();
    await expect(page.getByText("Loading reports", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Try again" })).toHaveCount(0);
    await expect(page.getByText("locations ready to compare", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Available reports" })).toBeVisible();
    await expect(
      page.locator("button").filter({
        hasText: /(?:Onboarding baseline|Month \d+) report/,
      }).first(),
    ).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "What matters for your business today" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Open navigation menu" }).click();

    const mobileNavigation = page.getByRole("navigation", { name: "Product navigation" });
    await expect(mobileNavigation).toBeVisible();
    await expect(mobileNavigation.getByText("Most used", { exact: true })).toBeVisible();
    await expect(mobileNavigation.getByText("Measure performance", { exact: true })).toBeVisible();
    await expect(mobileNavigation.getByText("Improve visibility", { exact: true })).toBeVisible();
    await expect(mobileNavigation.getByText("Manage workspace", { exact: true })).toBeVisible();
    await expect(mobileNavigation.getByText("More tools", { exact: true })).toHaveCount(0);
    expect(browserProblemTypes).toEqual([]);
  } finally {
    if (logoutUrl) {
      const logoutResponse = await page.request.post(logoutUrl, {
        failOnStatusCode: false,
      });
      expect(logoutResponse.ok(), "The smoke session must be revoked after the run.").toBeTruthy();
      const logoutPayload = await logoutResponse.json();
      expect(
        logoutPayload?.data?.session_revoked,
        "The backend must confirm that the smoke session was revoked.",
      ).toBe(true);
    }
    await page.context().clearCookies();
  }
});
