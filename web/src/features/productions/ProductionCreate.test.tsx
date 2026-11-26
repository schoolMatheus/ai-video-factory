import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../app/App";
import { Providers } from "../../app/providers";
import { routes } from "../../app/router";
import { capturedIdempotencyKeys } from "../../test/handlers";
import { server } from "../../test/setup";

function renderCreate() {
  const router = createMemoryRouter(routes, { initialEntries: ["/novo"] });
  return render(
    <Providers>
      <App router={router} />
    </Providers>,
  );
}

describe("ProductionCreate", () => {
  beforeEach(() => {
    capturedIdempotencyKeys.length = 0;
  });

  it("reutiliza a mesma chave em cliques repetidos", async () => {
    const user = userEvent.setup();
    renderCreate();

    await user.type(screen.getByLabelText("Tema"), "Documentário sobre astronomia");
    const button = await waitFor(() =>
      screen.getByRole("button", { name: "Iniciar produção" }),
    );
    await waitFor(() => expect(button).toBeEnabled());

    await user.click(button);
    await user.click(button);

    await waitFor(() => expect(capturedIdempotencyKeys.length).toBeGreaterThan(0));
    expect(capturedIdempotencyKeys.every(Boolean)).toBe(true);
    expect(new Set(capturedIdempotencyKeys).size).toBe(1);
  });

  it("desabilita início quando preflight aponta pendência", async () => {
    server.use(
      http.post("/api/v1/productions/preflight", () =>
        HttpResponse.json({
          can_start: false,
          through: null,
          actions: [],
          problems: [
            {
              code: "staged_flow_unavailable",
              message: "Fluxo de seis etapas não configurado.",
              recoverable: true,
              suggested_action: null,
              diagnostic_reference: null,
            },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    renderCreate();

    await user.type(screen.getByLabelText("Tema"), "Sem fluxo");

    expect(await screen.findByText("Fluxo de seis etapas não configurado.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Iniciar produção" })).toBeDisabled();
    expect(capturedIdempotencyKeys).toHaveLength(0);
  });

  it("salva rascunho sem iniciar execução", async () => {
    const user = userEvent.setup();
    renderCreate();

    await user.type(screen.getByLabelText("Tema"), "Rascunho");
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));

    expect(await screen.findByText("Rascunho salvo, sem execução.")).toBeInTheDocument();
    expect(capturedIdempotencyKeys).toHaveLength(0);
  });
});
