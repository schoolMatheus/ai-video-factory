import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Providers } from "../../app/providers";
import { SettingsPage } from "./SettingsPage";

function renderSettings() {
  return render(
    <Providers>
      <SettingsPage />
    </Providers>,
  );
}

describe("Configurações", () => {
  it("mostra a configuração lida do servidor", async () => {
    renderSettings();

    expect(
      await screen.findByRole("heading", { name: "Configurações", level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText("v1")).toBeInTheDocument();

    const legacy = screen.getByRole("row", { name: /Leitura de produções legadas/i });
    expect(within(legacy).getByText("Disponível")).toBeInTheDocument();

    const stages = screen.getByRole("row", { name: /Fluxo de seis etapas/i });
    expect(within(stages).getByText("Indisponível")).toBeInTheDocument();
  });

  it("não oferece alteração de configuração", async () => {
    renderSettings();

    await screen.findByRole("heading", { name: "Configurações", level: 1 });
    expect(screen.queryByRole("button", { name: /salvar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
