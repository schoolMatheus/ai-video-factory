import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "../../app/App";
import { Providers } from "../../app/providers";
import { routes } from "../../app/router";

function renderMemory(profile: string) {
  const router = createMemoryRouter(routes, {
    initialEntries: [`/memoria?perfil=${profile}`],
  });
  return render(
    <Providers>
      <App router={router} />
    </Providers>,
  );
}

describe("MemoryList", () => {
  it("não mistura aprendizados entre canais", async () => {
    renderMemory("canal-a");

    expect(await screen.findByText("Regra ativa do canal A")).toBeInTheDocument();
    expect(screen.queryByText("Hipótese do canal B")).not.toBeInTheDocument();
  });

  it("distingue hipótese de regra ativa e mostra evidência", async () => {
    renderMemory("canal-a");

    expect(await screen.findByText("Estado: active")).toBeInTheDocument();
    expect(screen.getByText("evidencia-a")).toBeInTheDocument();
    expect(screen.getByText("Origem: inferência do agente")).toBeInTheDocument();
  });

  it("permite filtrar por etapa", async () => {
    const user = userEvent.setup();
    renderMemory("canal-a");

    await user.selectOptions(await screen.findByLabelText("Etapa"), "media");

    expect(screen.queryByText("Regra ativa do canal A")).not.toBeInTheDocument();
  });
});
