import { expect, test, type Page, type APIRequestContext } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
  await expect(page.getByRole("heading", { name: "Produções" })).toBeVisible();
}

test("abre o painel e mostra pendência de capacidade", async ({ page, request }) => {
  await openDashboard(page, request);

  await page.getByRole("link", { name: "Nova produção" }).first().click();
  await page.getByLabel("Tema").fill("Episódio de teste");
  await expect(page.getByRole("button", { name: "Iniciar produção" })).toBeDisabled();
  await expect(page.getByText(/fluxo de seis etapas/i)).toBeVisible();
});
