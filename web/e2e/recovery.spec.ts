import { expect, test, type Page, type APIRequestContext } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
}

test("recupera o estado real após atualizar a página", async ({ page, request }) => {
  await openDashboard(page, request);
  const seeded = await request.post("/__e2e/seed");
  const { production_id } = (await seeded.json()) as { production_id: string };

  await page.goto(`/producoes/${production_id}`);
  await expect(page.getByText("2 de 6 etapas concluídas")).toBeHidden();
  await expect(page.getByRole("navigation", { name: "Etapas da produção" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Episódio E2E" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Etapas da produção" })).toBeVisible();
});
