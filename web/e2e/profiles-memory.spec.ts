import { expect, test, type Page, type APIRequestContext } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  await request.post("/__e2e/seed-profiles");
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
}

test("perfis e memória não misturam canais", async ({ page, request }) => {
  await openDashboard(page, request);

  await page.goto("/perfis");
  await expect(page.getByRole("heading", { name: "Perfis" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Canal canal-a" })).toBeVisible();

  await page.goto("/memoria?perfil=canal-a");
  await expect(page.getByText("Abertura longa demais")).toBeVisible();

  await page.goto("/memoria?perfil=canal-b");
  await expect(page.getByText("Abertura longa demais")).toHaveCount(0);
});
