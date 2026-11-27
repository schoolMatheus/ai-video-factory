import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getProduction,
  getStageBundle,
  listEvents,
  requestProductionAction,
  type StageBundle,
} from "../../api/client";
import { ProductionEventStream, type StreamStatus } from "../../api/events";
import { queryKeys } from "../../api/queryKeys";
import { API_PREFIX } from "../../api/types";
import type {
  ActionAvailability,
  ArtifactView,
  EventView,
  Progress,
  StageName,
  StageView,
} from "../../api/types";
import { ActivityFeed } from "../../components/ActivityFeed";
import { ArtifactViewer } from "../../components/ArtifactViewer";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import { StageList } from "../../components/StageList";
import { StatusText } from "../../components/StatusText";
import { EditingView } from "../stages/EditingView";
import { MediaView } from "../stages/MediaView";
import { NarrationView } from "../stages/NarrationView";
import { ResearchView } from "../stages/ResearchView";
import { ReviewView } from "../stages/ReviewView";
import { ScriptView } from "../stages/ScriptView";
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

type BundleRecord = Record<string, any>;

function records(value: unknown): BundleRecord[] {
  return Array.isArray(value) ? (value as BundleRecord[]) : [];
}

function inspectorData(bundle: StageBundle | null, name: StageName): Record<string, unknown> {
  const data = (bundle ?? {}) as BundleRecord;
  switch (name) {
    case "research":
      return {
        claims: records(data.claims).map((claim) => ({
          text: String(claim.text ?? claim.claim_id ?? ""),
          evidence: records(claim.evidence).map((item) => String(item.quote ?? item)),
          contradictions: records(data.contradictions).map((item) => String(item.nature ?? item.reason ?? "")),
        })),
      };
    case "script":
      return {
        scenes: records(data.scenes).map((scene) => ({
          scene_id: String(scene.scene_id ?? ""),
          spoken: String(scene.narration_text ?? ""),
          direction: records(scene.shots).map((shot) => String(shot.visual ?? "")).join(" · "),
          sources: records(scene.shots).flatMap((shot) => records(shot.claim_refs).map(String)),
        })),
      };
    case "narration":
      return {
        segments: records(data.segments).map((segment) => ({
          id: String(segment.segment_id ?? ""),
          text: String(segment.text ?? ""),
          duration_seconds: Number(segment.duration_seconds ?? 0) || null,
          content_url: String(segment.audio?.path ?? ""),
        })),
      };
    case "media":
      return {
        shots: records(data.selected).map((selection) => {
          const candidate = records(data.candidates).find(
            (item) => item.candidate_id === selection.candidate_id,
          ) ?? {};
          return {
            shot_id: String(selection.shot_id ?? ""),
            source: String(candidate.url ?? candidate.title ?? "origem não informada"),
            license: String(candidate.license ?? "sem licença"),
            content_url: selection.file?.path
              ? `${API_PREFIX}/artifacts/${encodeURIComponent(String(selection.file.path))}/content`
              : null,
          };
        }),
      };
    case "review":
      return {
        checks: records(data.checks).map((check) => ({
          name: String(check.name ?? ""),
          measured: Boolean(check.passed),
          passed: Boolean(check.passed),
        })),
      };
    default:
      return {};
  }
}

function StageInspector({
  stage,
  actions,
  bundle,
  onAction,
}: {
  stage: StageView | undefined;
  actions: ActionAvailability[];
  bundle: StageBundle | null;
  onAction: (action: string, payload?: Record<string, unknown>) => void;
}) {
  if (!stage) return <p>Selecione uma etapa.</p>;
  const progress = formatProgress(stage.progress);
  return (
    <section className={styles.inspector} aria-label={`Detalhes da etapa ${STAGE_LABELS[stage.name]}`}>
      <h2>{STAGE_LABELS[stage.name]}</h2>
      <StatusText status={stage.status} />
      {stage.activity && <p>{stage.activity}</p>}
      {progress && <p className={styles.data}>{progress}</p>}
      {stage.last_activity_at && (
        <p className={styles.support}>Última atividade: {stage.last_activity_at}</p>
      )}
      {stage.problem && (
        <InlineError
          message={stage.problem.message}
          onRetry={stage.problem.recoverable ? () => void onAction("resume") : undefined}
        />
      )}
      {stage.name === "research" && (
        <ResearchView claims={inspectorData(bundle, stage.name).claims as never} />
      )}
      {stage.name === "script" && (
        <ScriptView scenes={inspectorData(bundle, stage.name).scenes as never} />
      )}
      {stage.name === "narration" && (
        <NarrationView segments={inspectorData(bundle, stage.name).segments as never} />
      )}
      {stage.name === "media" && (
        <MediaView shots={inspectorData(bundle, stage.name).shots as never} />
      )}
      {stage.name === "editing" && (
        <EditingView
          actions={actions}
          bundle={bundle}
          onOpen={() => onAction("open_editor")}
          onReconcile={() => onAction("reconcile_editor")}
        />
      )}
      {stage.name === "review" && (
        <ReviewView checks={inspectorData(bundle, stage.name).checks as never} bundle={bundle} />
      )}
    </section>
  );
}

function StageArtifacts({
  artifacts,
  onShowFiles,
}: {
  artifacts: ArtifactView[];
  onShowFiles: () => void;
}) {
  if (artifacts.length === 0) {
    return (
      <p className={styles.artifactEmpty}>
        Nenhum artefato neste estágio.
        <button type="button" className={styles.textAction} onClick={onShowFiles}>
          Ver todos os arquivos
        </button>
      </p>
    );
  }

  return (
    <ul className={styles.artifactList}>
      {artifacts.map((artifact) => (
        <li key={artifact.id} className={styles.artifactRow}>
          <a
            href={`${API_PREFIX}/artifacts/${encodeURIComponent(artifact.id)}/content`}
            download={artifact.name}
          >
            {artifact.name}
          </a>
          <span className={styles.artifactState}>
            {artifact.integrity === "verified" ? "verificado" : "sem registro"}
          </span>
        </li>
      ))}
    </ul>
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
  const bundle = useQuery({
    queryKey: queryKeys.bundle(productionId, selected),
    queryFn: () => getStageBundle(productionId, selected),
    retry: false,
  });

  const actionKeys = useRef(new Map<string, string>());
  async function runAction(action: string, payload: Record<string, unknown> = {}) {
    const identity = `${action}:${JSON.stringify(payload)}`;
    const key = actionKeys.current.get(identity) ?? `${productionId}:${identity}`;
    actionKeys.current.set(identity, key);
    try {
      await requestProductionAction(productionId, action, payload, key);
      await queryClient.invalidateQueries({ queryKey: queryKeys.production(productionId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.events(productionId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bundle(productionId, selected) });
    } catch {
      setStreamStatus("offline");
    }
  }

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
          // Named events change the persisted snapshot or its artifacts:
          // re-read the backend instead of only appending to the feed.
          if (
            event.type === "production.updated" ||
            event.type.startsWith("stage.") ||
            event.type === "artifact.available" ||
            event.type === "memory.updated"
          ) {
            void queryClient.invalidateQueries({
              queryKey: queryKeys.production(productionId),
            });
          }
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
  const stageNumber = stages.findIndex((item) => item.name === selected) + 1;
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
          <Button
            variant="primary"
            disabled={!resume?.enabled}
            title={resume?.reason ?? undefined}
            onClick={() => void runAction("resume")}
          >
            Retomar
          </Button>
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
          <div className={styles.stageColumn}>
            <p className={styles.count}>{completed} de 6 etapas concluídas</p>
            <StageList stages={stages} selected={selected} onSelect={setSelected} />
          </div>
          <div className={styles.contentColumn}>
            <p className={styles.stageMeta}>
              Etapa {stageNumber} de 6 · <span className={styles.data}>{productionId}</span>
            </p>
            <StageInspector
              stage={stage}
              actions={snapshot.data.capabilities ?? []}
              bundle={bundle.data ?? null}
              onAction={(action, payload) => void runAction(action, payload)}
            />
          </div>
          <aside className={styles.artifactColumn} aria-label="Artefatos do estágio">
            <h2 className={styles.artifactHeading}>Artefatos do estágio</h2>
            <StageArtifacts
              artifacts={stage?.artifacts ?? []}
              onShowFiles={() => setTab("files")}
            />
          </aside>
        </div>
      )}
      {tab === "files" && (
        <ul className={styles.artifactList}>
          {(snapshot.data.artifacts ?? []).map((artifact) => (
            <li key={artifact.id} className={styles.fileRow}>
              <ArtifactViewer artifact={artifact} />
            </li>
          ))}
          {!snapshot.data.artifacts?.length && (
            <li className={styles.fileRow}>Nenhum arquivo confirmado ainda.</li>
          )}
        </ul>
      )}
      {tab === "history" && <ActivityFeed events={events} />}
      {tab === "memory" && (
        <p>Memória utilizada ainda não disponível para esta produção.</p>
      )}
    </section>
  );
}
