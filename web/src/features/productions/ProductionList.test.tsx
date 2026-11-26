import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { App } from "../../app/App";
import { Providers } from "../../app/providers";
import { routes } from "../../app/router";
import { server } from "../../test/setup";

function renderList() {
  const router = createMemoryRouter(routes, { initialEntries: ["/producoes"] });
  return render(
    <Providers>
      <App router={router} />
    </Providers>,
  );
}

describe("ProductionList", () => {
  it("separa resultados por canal", async () => {
    const user = userEvent.setup();
    renderList();

    await user.type(screen.getByLabelText("Canal"), "canal-a");
    expect(await screen.findByText("Tema do canal A")).toBeInTheDocument();

    const input = screen.getByLabelText("Canal");
    await user.clear(input);
    await user.type(input, "canal-b");

    expect(await screen.findByText("Tema do canal B")).toBeInTheDocument();
    expect(screen.queryByText("Tema do canal A")).not.toBeInTheDocument();
  });

  it("mostra erro recuperável com nova tentativa", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json(
          {
            code: "service_unavailable",
            message: "Serviço indisponível",
            recoverable: true,
            suggested_action: null,
            diagnostic_reference: null,
          },
          { status: 503 },
        ),
      ),
    );
    renderList();

    expect(await screen.findByRole("alert")).toHaveTextContent("Serviço indisponível");

    server.resetHandlers();
    await userEvent.setup().click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByText("Nenhuma produção ainda.")).toBeInTheDocument();
  });
});
