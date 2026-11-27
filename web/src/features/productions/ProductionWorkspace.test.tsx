import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { API_PREFIX } from "../../api/types";
import { App } from "../../app/App";
import { Providers } from "../../app/providers";
import { routes } from "../../app/router";
import type { StageView } from "../../api/types";
import { FakeEventSource, server } from "../../test/setup";
import { setCurrentProduction } from "../../test/handlers";

function stage(name: StageView["name"], status: StageView["status"], progress?: StageView["progress"]): StageView {
  return {
    name,
    status,
    activity: null,
    artifacts: [],
    last_activity_at: null,
    observed: true,
    problem: null,
    progress: progress ?? null,
    started_at: null,
    updated_at: null,
  };
}

function renderWorkspace() {
  const router = createMemoryRouter(routes, {
    initialEntries: [`/producoes/${"d".repeat(32)}`],
  });
  return render(
    <Providers>
      <App router={router} />
    </Providers>,
  );
}

describe("ProductionWorkspace", () => {
  beforeEach(() => {
    FakeEventSource.instances.length = 0;
    server.resetHandlers();
    setCurrentProduction({
      id: "d".repeat(32),
      mode: "legacy",
      title: "Produção real",
      topic: "Tema",
      profile_id: "canal-a",
      profile_revision: null,
      snapshot_id: null,
      state: "running",
      observed_stages: ["research"],
      stages: [
        stage("research", "completed"),
        stage("script", "completed"),
        stage("narration", "running", {
          completed: 12,
          total: null,
          unit: "segments",
          source: "narration_bundle.json",
        }),
        stage("media", "unknown"),
        stage("editing", "unknown"),
        stage("review", "unknown"),
      ],
      artifacts: [],
      capabilities: [
        {
          action: "resume",
          enabled: true,
          reason: null,
        },
      ],
      problems: [],
      started_at: null,
      updated_at: "2026-11-23T00:00:00+00:00",
      cursor: null,
    });
  });

  it("conta etapas sem transformar em percentual de tempo", async () => {
    renderWorkspace();

    expect(await screen.findByText("2 de 6 etapas concluídas")).toBeInTheDocument();
    expect(screen.queryByText(/33%/)).not.toBeInTheDocument();
  });

  it("mostra atividade indeterminada sem percentual inventado", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    expect(await screen.findByText("2 de 6 etapas concluídas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Narração/ }));

    expect(screen.getByText("12 segments")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("preserva a seleção de etapa quando eventos chegam", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await user.click(await screen.findByRole("button", { name: /Mídia/ }));

    act(() => {
      FakeEventSource.instances[0]?.onmessage?.(
        { data: JSON.stringify({ stage: "research" }), lastEventId: "event-1" } as MessageEvent<string>,
      );
    });

    expect(screen.getByRole("button", { name: /Mídia/ })).toHaveAttribute(
      "aria-current",
      "step",
    );
  });

  it("mantém dados com aviso quando a conexão cai e converge depois", async () => {
    renderWorkspace();

    expect(await screen.findByText("2 de 6 etapas concluídas")).toBeInTheDocument();
    act(() => {
      const source = FakeEventSource.instances[0];
      source?.onerror?.();
      source?.onerror?.();
      source?.onerror?.();
    });

    expect(
      await screen.findByText("Sem conexão — dados da última atualização"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 de 6 etapas concluídas")).toBeInTheDocument();

    act(() => {
      FakeEventSource.instances[0]?.onopen?.();
    });

    await waitFor(() =>
      expect(
        screen.queryByText("Sem conexão — dados da última atualização"),
      ).not.toBeInTheDocument(),
    );
  });

  it("habilita retomada somente quando a capacidade está disponível", async () => {
    renderWorkspace();

    const button = await screen.findByRole("button", { name: "Retomar" });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("atualiza o snapshot quando um evento nomeado chega", async () => {
    renderWorkspace();
    expect(await screen.findByText("Produção real")).toBeInTheDocument();

    setCurrentProduction({
      id: "d".repeat(32),
      mode: "legacy",
      title: "Produção atualizada",
      topic: "Tema",
      profile_id: "canal-a",
      profile_revision: null,
      snapshot_id: null,
      state: "completed",
      observed_stages: ["research"],
      stages: [],
      artifacts: [],
      capabilities: [],
      problems: [],
      started_at: null,
      updated_at: "2026-11-26T00:00:00+00:00",
      cursor: null,
    });
    act(() => {
      FakeEventSource.instances[0]?.emit("stage.completed", "{}", "evt-2");
    });

    expect(await screen.findByText("Produção atualizada")).toBeInTheDocument();
  });

  it("mostra entregas reais de todas as etapas na mesma jornada", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await screen.findByText("2 de 6 etapas concluídas");

    expect(await screen.findByText("Afirmação sustentada")).toBeInTheDocument();
    expect(screen.getByText("trecho real")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Roteiro/ }));
    expect(await screen.findByText("Fala canônica")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Narração/ }));
    expect(await screen.findByText(/Duração medida: 2s/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Mídia/ }));
    expect(await screen.findByText(/CC-BY/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Edição/ }));
    expect(await screen.findByText(/projeto.fcproj/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Revisão/ }));
    expect(await screen.findByText(/duração: passou/)).toBeInTheDocument();
  });

  it("executa ação de retomada e atualiza a consulta da produção", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    const button = await screen.findByRole("button", { name: "Retomar" });
    await user.click(button);
    await waitFor(() => expect(button).toBeInTheDocument());
  });

  it("reusa a mesma chave em dois cliques rápidos de retomada", async () => {
    const keys: (string | null)[] = [];
    server.use(
      http.post(`${API_PREFIX}/productions/:id/actions`, ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.json({
          job_id: "job-1", production_id: "p".repeat(32), status: "queued",
        });
      }),
    );
    const user = userEvent.setup();
    renderWorkspace();
    const button = await screen.findByRole("button", { name: "Retomar" });

    await Promise.all([user.click(button), user.click(button)]);
    await waitFor(() => expect(keys.length).toBeGreaterThan(0));

    expect(keys[0]).toBeTruthy();
    expect(new Set(keys).size).toBe(1);
  });

  it("não mistura eventos de outra produção", async () => {
    renderWorkspace();

    await screen.findByText("2 de 6 etapas concluídas");
    act(() => {
      FakeEventSource.instances[0]?.onmessage?.(
        {
          data: JSON.stringify({ stage: "media" }),
          lastEventId: "event-other",
        } as MessageEvent<string>,
      );
    });

    await userEvent.setup().click(screen.getByRole("tab", { name: "Histórico" }));
    expect(screen.queryByText(/media/)).not.toBeInTheDocument();
  });
});
