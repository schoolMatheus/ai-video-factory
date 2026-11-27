import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

async function openDashboard(page: Page, request: APIRequestContext) {
  await request.post("/__e2e/seed-profiles");
  const response = await request.post("/__e2e/token");
  const { token } = (await response.json()) as { token: string };
  await page.goto(`/#token=${token}`);
}

test("clique em iniciar atravessa API, worker e coordenador reais", async ({
  page,
  request,
}) => {
  await openDashboard(page, request);

  await page.getByRole("link", { name: "Produções" }).click();
  await page.getByRole("link", { name: "Nova produção" }).first().click();
  await page.getByLabel("Canal / perfil").fill("canal-a");
  await page.getByLabel("Tema", { exact: true }).fill("Jornadareal E2E");

  const submitted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/productions") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Iniciar produção" }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const receipt = (await response.json()) as {
    job_id: string;
    production_id: string;
  };

  const finished = await request.post(`/__e2e/run-job/${receipt.job_id}`);
  expect(finished.status()).toBe(200);
  expect((await finished.json()).status).toBe("completed");

  const job = await page.request.get(`/api/v1/jobs/${receipt.job_id}`);
  expect(job.status()).toBe(200);
  expect((await job.json()).status).toBe("completed");

  await page.reload();
  await expect(page.getByText(/6 de 6 etapas concluídas/)).toBeVisible();
  await page.getByRole("button", { name: /Roteiro/ }).click();
  await expect(page.getByText("Fala E2E.")).toBeVisible();
});
