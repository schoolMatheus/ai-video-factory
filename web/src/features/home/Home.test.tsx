import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { Providers } from "../../app/providers";
import type { ProductionView } from "../../api/types";
import { server } from "../../test/setup";
import { Home } from "./Home";

const productionFixture: ProductionView = {
  id: "d".repeat(32),
  mode: "legacy",
  title: "Produção em acompanhamento",
  state: "running",
  profile_id: "canal-a",
  stages: [],
  artifacts: [],
  capabilities: [],
  problems: [],
  observed_stages: [],
  started_at: null,
  updated_at: null,
  cursor: null,
};

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Providers>
        <Home />
      </Providers>
    </MemoryRouter>,
  );
}

describe("Home", () => {
  beforeEach(() => server.resetHandlers());

  it("mostra produção em andamento com etapas observadas", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({
          items: [
            {
              ...productionFixture,
              state: "running",
              stages: [
                { name: "research", status: "completed" },
                { name: "script", status: "completed" },
                { name: "narration", status: "running" },
              ],
            },
          ],
          next_cursor: null,
        }),
      ),
    );

    renderHome();

    expect(await screen.findByText("2 de 6 etapas concluídas")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("busca eventos de uma única produção", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({ items: [productionFixture], next_cursor: null }),
      ),
    );
    let calls = 0;
    server.use(
      http.get("/api/v1/productions/:id/events", () => {
        calls += 1;
        return HttpResponse.json({
          items: [
            {
              id: "e1",
              production_id: productionFixture.id,
              type: "stage.started",
              timestamp: "2026-11-26T18:42:00+00:00",
              scope: "production",
              severity: "info",
            },
          ],
          next_cursor: null,
        });
      }),
    );

    renderHome();

    await screen.findByText("stage.started");
    expect(calls).toBe(1);
  });

  it("mostra nichos cadastrados", async () => {
    renderHome();
    expect(await screen.findByText("astronomia")).toBeInTheDocument();
  });

  it("reserva espaço para notícias sem inventar conteúdo", async () => {
    renderHome();
    expect(
      await screen.findByText(
        "Sem fonte conectada. Espaço reservado para notícias dos nichos.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /notícia/i })).not.toBeInTheDocument();
  });

  it("mostra estado vazio honesto sem produções", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );

    renderHome();

    expect(
      await screen.findByText("Nenhuma produção em andamento."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Nenhuma atividade registrada."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/de 6 etapas concluídas/)).not.toBeInTheDocument();
  });

  it("mostra só as produções em andamento", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({
          items: [
            {
              ...productionFixture,
              id: "1".repeat(32),
              title: "Produção ativa",
              state: "running",
              profile_id: "canal-a",
            },
            {
              ...productionFixture,
              id: "2".repeat(32),
              title: "Produção concluída",
              state: "completed",
              profile_id: "canal-b",
            },
          ],
          next_cursor: null,
        }),
      ),
    );

    renderHome();

    expect(await screen.findByText("Produção ativa")).toBeInTheDocument();
    expect(screen.queryByText("Produção concluída")).not.toBeInTheDocument();
    expect(screen.getByText("canal-a")).toBeInTheDocument();
  });

  it("identifica produção sem perfil como legado", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({
          items: [{ ...productionFixture, profile_id: null }],
          next_cursor: null,
        }),
      ),
    );

    renderHome();

    expect(await screen.findByText("Legado — sem perfil")).toBeInTheDocument();
  });

  it("mostra os seis eventos mais recentes", async () => {
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({ items: [productionFixture], next_cursor: null }),
      ),
    );
    server.use(
      http.get("/api/v1/productions/:id/events", () =>
        HttpResponse.json({
          items: Array.from({ length: 7 }, (_, index) => ({
            id: `e${index}`,
            production_id: productionFixture.id,
            type: `event-${index}`,
            timestamp: "2026-11-26T18:42:00+00:00",
            scope: "production",
            severity: "info",
          })),
          next_cursor: null,
        }),
      ),
    );

    renderHome();

    await screen.findByText("event-6");
    expect(screen.queryByText("event-0")).not.toBeInTheDocument();
    expect(screen.getAllByText(/^event-\d$/)).toHaveLength(6);
  });

  it("não mostra contagem quando nenhum estágio foi observado", async () => {
    const stages = [
      "research",
      "script",
      "narration",
      "media",
      "editing",
      "review",
    ].map((name) => ({ name, status: "unknown", observed: false }));
    server.use(
      http.get("/api/v1/productions", () =>
        HttpResponse.json({
          items: [{ ...productionFixture, state: "running", stages }],
          next_cursor: null,
        }),
      ),
    );

    renderHome();

    expect(await screen.findByText("Produção em acompanhamento")).toBeInTheDocument();
    expect(screen.queryByText(/de 6 etapas concluídas/)).not.toBeInTheDocument();
  });

  it("não anuncia ausência de atividade antes do carregamento", () => {
    renderHome();
    expect(screen.getByText("Carregando produções…")).toBeInTheDocument();
    expect(screen.queryByText("Nenhuma atividade registrada.")).not.toBeInTheDocument();
  });
});
