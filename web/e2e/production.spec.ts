import { expect, test, type Page, type APIRequestContext } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
  await expect(page.getByRole("heading", { name: "Início" })).toBeVisible();
}

test("abre o painel e mostra a capacidade real do preflight", async ({ page, request }) => {
  await openDashboard(page, request);

  await page.getByRole("link", { name: "Produções" }).click();
  await expect(page.getByRole("heading", { name: "Produções" })).toBeVisible();
  await page.getByRole("link", { name: "Nova produção" }).first().click();
  await page.getByLabel("Tema").fill("Episódio de teste");
  await expect(page.getByText(/Execução possível até: (review|mídia)/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Iniciar produção" })).toBeEnabled();
  await expect(page.getByText(/fluxo de seis etapas ainda não está configurado/i)).toHaveCount(0);
});
