import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { addFeedback, listMemory, suspendLearning } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { MemoryView, StageName } from "../../api/types";
import { InlineError } from "../../components/InlineError";
import { LearningDetails } from "./LearningDetails";
import styles from "./MemoryList.module.css";

const STAGES: Array<StageName | "all"> = [
  "all",
  "research",
  "script",
  "narration",
  "media",
  "editing",
  "review",
];
const STATES = ["all", "observed", "active", "suspended", "superseded"];

export function MemoryList() {
  const [searchParams] = useSearchParams();
  const profileId = searchParams.get("perfil") ?? "";
  const [stage, setStage] = useState("all");
  const [state, setState] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const query = useQuery({
    queryKey: [...queryKeys.memory(profileId), stage, state],
    queryFn: () => listMemory(profileId),
    enabled: Boolean(profileId),
    retry: false,
  });

  const items = (query.data?.items ?? []).filter(
    (item) =>
      (stage === "all" || item.stage === stage) &&
      (state === "all" || item.state === state),
  );
  const detail = items.find((item) => item.id === selected) ?? items[0];

  if (!profileId) return <p>Selecione um perfil para ver a memória.</p>;
  if (query.isPending) return <p>Carregando memória…</p>;
  if (query.isError) {
    return (
      <InlineError
        message="Não foi possível carregar a memória deste perfil."
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <section className={styles.page}>
      <h1>Memória do canal {profileId}</h1>
      <p>Mudanças automáticas aparecem aqui sem exigir aprovação humana.</p>
      <div className={styles.filters}>
        <label>
          Etapa
          <select value={stage} onChange={(event) => setStage(event.target.value)}>
            {STAGES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado
          <select value={state} onChange={(event) => setState(event.target.value)}>
            {STATES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>
      {items.length === 0 && <p>Nenhum aprendizado corresponde a este filtro.</p>}
      <div className={styles.columns}>
        <ul>
          {items.map((item: MemoryView) => (
            <li key={item.id}>
              <button type="button" onClick={() => setSelected(item.id)}>
                {item.summary} — {item.state}
              </button>
            </li>
          ))}
        </ul>
        <div>
          {detail ? <LearningDetails item={detail} /> : <p>Selecione um item.</p>}
          {detail && (
            <button
              type="button"
              onClick={() =>
                void suspendLearning(profileId, detail.id, 1, "Suspensão manual pelo operador").then(
                  () => query.refetch(),
                )
              }
            >
              Suspender aprendizado
            </button>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() =>
          void addFeedback(profileId, { summary: "Feedback registrado pelo operador", stage: "script" }).then(
            () => query.refetch(),
          )
        }
      >
        Registrar feedback
      </button>
    </section>
  );
}
