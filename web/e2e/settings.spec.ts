import { expect, test, type Page, type APIRequestContext } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
  await expect(page.getByRole("heading", { name: "Produções" })).toBeVisible();
}

test("abre configurações pelo menu e mostra a configuração real", async ({
  page,
  request,
}) => {
  await openDashboard(page, request);

  await page.getByRole("link", { name: "Configurações" }).click();

  await expect(page).toHaveURL(/\/configuracoes$/);
  await expect(
    page.getByRole("heading", { name: "Configurações", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("row", { name: /Leitura de produções legadas/i }),
  ).toContainText("Disponível");
});
