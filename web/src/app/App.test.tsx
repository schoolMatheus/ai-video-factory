import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { Providers } from "./providers";
import { routes } from "./router";

function renderApp() {
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  return render(
    <Providers>
      <App router={router} />
    </Providers>,
  );
}

describe("App shell", () => {
  it("navega por teclado até o conteúdo principal", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.tab();

    expect(screen.getByRole("link", { name: "Ir para o conteúdo" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Produções" })).toHaveFocus();
  });

  it("mostra estado vazio com ação Nova produção", async () => {
    renderApp();

    expect(await screen.findByText("Nenhuma produção ainda.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Nova produção" }).length).toBeGreaterThan(0);
  });

  it("oferece limpar filtro quando não há resultados para o filtro", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("Canal"), "canal-inexistente");

    expect(await screen.findByText("Nenhuma produção neste filtro.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpar filtro" })).toBeInTheDocument();
  });

  it("abre configurações pelo menu principal", async () => {
    const user = userEvent.setup();
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });
    render(
      <Providers>
        <App router={router} />
      </Providers>,
    );

    await user.click(screen.getByRole("link", { name: "Configurações" }));

    expect(
      await screen.findByRole("heading", { name: "Configurações", level: 1 }),
    ).toBeInTheDocument();
  });
});
