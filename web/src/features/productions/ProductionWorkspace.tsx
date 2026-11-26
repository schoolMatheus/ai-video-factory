import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getProduction, listEvents } from "../../api/client";
import { ProductionEventStream, type StreamStatus } from "../../api/events";
import { queryKeys } from "../../api/queryKeys";
import type { EventView, Progress, StageName, StageView } from "../../api/types";
import { ActivityFeed } from "../../components/ActivityFeed";
import { ArtifactViewer } from "../../components/ArtifactViewer";
import { InlineError } from "../../components/InlineError";
import { StageList } from "../../components/StageList";
import { StatusText } from "../../components/StatusText";
import styles from "./ProductionWorkspace.module.css";

const STAGE_LABELS: Record<StageName, string> = {
  research: "Pesquisa",
  script: "Roteiro",
  narration: "Narração",
  media: "Mídia",
  editing: "Edição",
  review: "Revisão",
};

function formatProgress(progress: Progress | null | undefined): string | null {
  if (!progress) return null;
  const unit = progress.unit;
  if (progress.total === null || progress.total === undefined) {
    return `${progress.completed} ${unit}`;
  }
  return `${progress.completed} de ${progress.total} ${unit}`;
}

function StageInspector({ stage }: { stage: StageView | undefined }) {
  if (!stage) return <p>Selecione uma etapa.</p>;
  const progress = formatProgress(stage.progress);
  return (
    <section aria-label={`Detalhes da etapa ${STAGE_LABELS[stage.name]}`}>
      <h2>{STAGE_LABELS[stage.name]}</h2>
      <StatusText status={stage.status} />
      {stage.activity && <p>{stage.activity}</p>}
      {progress && <p>{progress}</p>}
      {stage.last_activity_at && (
        <p className={styles.support}>Última atividade: {stage.last_activity_at}</p>
      )}
      {stage.problem && (
        <InlineError
          message={stage.problem.message}
          onRetry={stage.problem.recoverable ? () => undefined : undefined}
        />
      )}
      {(stage.artifacts ?? []).map((artifact) => (
        <ArtifactViewer key={artifact.id} artifact={artifact} />
      ))}
    </section>
  );
}

export function ProductionWorkspace() {
  const { productionId = "" } = useParams();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<StageName>("research");
  const [tab, setTab] = useState<"stages" | "files" | "history" | "memory">("stages");
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const [events, setEvents] = useState<EventView[]>([]);

  const snapshot = useQuery({
    queryKey: queryKeys.production(productionId),
    queryFn: () => getProduction(productionId),
    retry: false,
  });
  const eventPage = useQuery({
    queryKey: queryKeys.events(productionId),
    queryFn: () => listEvents(productionId),
    retry: false,
  });

  useEffect(() => {
    if (!eventPage.data) return;
    setEvents(eventPage.data.items ?? []);
  }, [eventPage.data]);

  useEffect(() => {
    if (!snapshot.data) return;
    const stream = new ProductionEventStream(
      productionId,
      {
        onEvent: (event) => {
          if (event.production_id !== productionId) return;
          setEvents((current) => [...current, event]);
        },
        onStatus: setStreamStatus,
        onSnapshotRequired: () => {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.production(productionId),
          });
          void queryClient.invalidateQueries({
            queryKey: queryKeys.events(productionId),
          });
        },
      },
      snapshot.data.cursor ?? null,
    );
    stream.connect();
    return () => stream.close();
  }, [productionId, queryClient, snapshot.data]);

  // Polling fallback while SSE is down; paused when the tab is hidden.
  useEffect(() => {
    if (streamStatus !== "offline") return;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.production(productionId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.events(productionId),
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [productionId, queryClient, streamStatus]);

  const stages = snapshot.data?.stages ?? [];
  const stage = useMemo(
    () => stages.find((item) => item.name === selected),
    [stages, selected],
  );
  const completed = stages.filter((item) => item.status === "completed").length;
  const resume = (snapshot.data?.capabilities ?? []).find(
    (item) => item.action === "resume",
  );

  if (snapshot.isPending) return <p>Carregando produção…</p>;
  if (snapshot.isError) {
    return (
      <InlineError
        message="Não foi possível carregar esta produção."
        onRetry={() => void snapshot.refetch()}
      />
    );
  }

  return (
    <section className={styles.workspace}>
      {streamStatus === "offline" && (
        <p role="status" className={styles.disconnected}>
          Sem conexão — dados da última atualização
        </p>
      )}
      <header className={styles.header}>
        <div>
          <h1>{snapshot.data.title}</h1>
          <p className={styles.support}>
            {snapshot.data.profile_id ?? "Legado — sem perfil"} · modo {snapshot.data.mode}
          </p>
        </div>
        <div className={styles.headerActions}>
          <StatusText status={snapshot.data.state} />
          <button type="button" disabled={!resume?.enabled} title={resume?.reason ?? undefined}>
            Retomar
          </button>
        </div>
      </header>

      <div className={styles.tabs} role="tablist" aria-label="Seções da produção">
        {(
          [
            ["stages", "Etapas"],
            ["files", "Arquivos"],
            ["history", "Histórico"],
            ["memory", "Memória utilizada"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "stages" && (
        <div className={styles.columns}>
          <div>
            <p className={styles.count}>{completed} de 6 etapas concluídas</p>
            <StageList stages={stages} selected={selected} onSelect={setSelected} />
          </div>
          <StageInspector stage={stage} />
        </div>
      )}
      {tab === "files" && (
        <ul>
          {(snapshot.data.artifacts ?? []).map((artifact) => (
            <li key={artifact.id}>
              <ArtifactViewer artifact={artifact} />
            </li>
          ))}
          {!snapshot.data.artifacts?.length && <li>Nenhum arquivo confirmado ainda.</li>}
        </ul>
      )}
      {tab === "history" && <ActivityFeed events={events} />}
      {tab === "memory" && (
        <p>Memória utilizada ainda não disponível para esta produção.</p>
      )}
    </section>
  );
}
