import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { InlineError } from "../../components/InlineError";

interface Tool {
  id: string;
  state: string;
  note: string | null;
}

const LABELS: Record<string, string> = {
  not_installed: "Não instalado",
  installed: "Instalado",
  configured: "Configurada",
  not_configured: "Não configurada",
  unavailable: "Indisponível",
  validated: "Validado",
  not_verified: "Não verificado",
};

export function ToolsPage() {
  const [results, setResults] = useState<Record<string, string>>({});
  const query = useQuery({
    queryKey: ["tools"],
    queryFn: async () => {
      const response = await fetch("/api/v1/tools", { credentials: "same-origin" });
      if (!response.ok) throw new Error("falha");
      return (await response.json()) as { items: Tool[] };
    },
    retry: false,
  });
  const check = useMutation({
    mutationFn: async (toolId: string) => {
      const csrf = document.cookie.match(/(?:^|;\s*)avf_session_csrf=([^;]+)/)?.[1];
      const response = await fetch(`/api/v1/tools/${toolId}/check`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": decodeURIComponent(csrf ?? "") },
      });
      if (!response.ok) throw new Error("falha");
      return (await response.json()) as { state: string; observed: string };
    },
    onSuccess: (data, toolId) =>
      setResults((current) => ({ ...current, [toolId]: `${LABELS[data.state] ?? data.state}: ${data.observed}` })),
  });

  return (
    <section>
      <h1>Ferramentas e diagnóstico</h1>
      <p>Testes de conexão só acontecem quando você solicita.</p>
      {query.isPending && <p>Carregando estado das ferramentas…</p>}
      {query.isError && <InlineError message="Não foi possível consultar as ferramentas." />}
      <ul>
        {(query.data?.items ?? []).map((tool) => (
          <li key={tool.id}>
            <span>
              {tool.id}: {LABELS[tool.state] ?? tool.state}
            </span>
            <button type="button" onClick={() => check.mutate(tool.id)}>
              Testar conexão
            </button>
            {results[tool.id] && <p role="status">{results[tool.id]}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
