import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MediaView } from "./MediaView";
import { NarrationView } from "./NarrationView";
import { ResearchView } from "./ResearchView";
import { ScriptView } from "./ScriptView";

describe("Stage inspectors", () => {
  it("mostra afirmação com evidência e contradição", () => {
    render(
      <ResearchView
        claims={[
          {
            text: "A fonte afirma X",
            evidence: ["trecho extraído", "https://example.test/fonte"],
            contradictions: ["outra fonte discorda"],
          },
        ]}
      />,
    );

    expect(screen.getByText("A fonte afirma X")).toBeInTheDocument();
    expect(screen.getByText("trecho extraído")).toBeInTheDocument();
    expect(screen.getByText(/outra fonte discorda/)).toBeInTheDocument();
  });

  it("mantém fala e direção em colunas distintas", () => {
    render(
      <ScriptView
        scenes={[
          {
            scene_id: "cena-1",
            spoken: "Texto exato falado",
            direction: "plano aberto, luz fria",
            sources: ["claim-1"],
          },
        ]}
      />,
    );

    const headers = screen.getAllByRole("columnheader").map((node) => node.textContent);
    expect(headers).toEqual(["Cena", "Fala", "Direção", "Fontes"]);
    expect(screen.getByText("Texto exato falado")).toBeInTheDocument();
  });

  it("renderiza Markdown externo como texto, sem HTML executável", () => {
    render(
      <ScriptView
        scenes={[
          {
            scene_id: "cena-2",
            spoken: "<script>alert(1)</script> **ênfase**",
            direction: "texto",
            sources: [],
          },
        ]}
      />,
    );

    expect(screen.getByText("<script>alert(1)</script> **ênfase**")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("oferece player por segmento com duração medida", () => {
    render(
      <NarrationView
        segments={[
          {
            id: "seg-1",
            text: "Primeira fala",
            duration_seconds: 4.2,
            content_url: "/api/v1/artifacts/abc/content",
          },
        ]}
      />,
    );

    expect(document.querySelector("audio")).not.toBeNull();
    expect(screen.getByText("Duração medida: 4.2s")).toBeInTheDocument();
  });

  it("mostra licença por plano de mídia", () => {
    render(
      <MediaView
        shots={[
          {
            shot_id: "shot-1",
            source: "Wikimedia",
            license: "CC BY-SA 4.0",
            content_url: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("Licença: CC BY-SA 4.0")).toBeInTheDocument();
  });

  it("comunica bundle ausente em vez de inventar conteúdo", () => {
    render(<ResearchView />);
    expect(screen.getByText(/Dossiê ainda não disponível/)).toBeInTheDocument();
  });
});
