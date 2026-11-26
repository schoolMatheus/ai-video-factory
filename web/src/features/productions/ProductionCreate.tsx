import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createProduction, preflightProduction } from "../../api/client";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import styles from "./ProductionCreate.module.css";

const DRAFT_KEY = "avf:production-draft";
const IDEMPOTENCY_KEY = "avf:create-idempotency-key";

function idempotencyKey(): string {
  const existing = sessionStorage.getItem(IDEMPOTENCY_KEY);
  if (existing) return existing;
  const generated =
    typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  sessionStorage.setItem(IDEMPOTENCY_KEY, generated);
  return generated;
}

export function ProductionCreate() {
  const navigate = useNavigate();
  const [profileId, setProfileId] = useState("");
  const [topic, setTopic] = useState("");
  const [angle, setAngle] = useState("");
  const [targetMinutes, setTargetMinutes] = useState("25");
  const [sources, setSources] = useState("");
  const [draftSaved, setDraftSaved] = useState(false);
  const submitting = useRef(false);

  const payload = useMemo(
    () => ({
      profile_id: profileId || null,
      topic,
      angle: angle || null,
      target_minutes: Number(targetMinutes) || null,
      seed_source_urls: sources
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    }),
    [profileId, topic, angle, targetMinutes, sources],
  );

  const preflight = useQuery({
    queryKey: ["preflight", topic, profileId, targetMinutes],
    queryFn: () => preflightProduction(payload),
    enabled: topic.trim().length > 0,
    retry: false,
  });

  const submit = useMutation({
    mutationFn: () => createProduction(payload, idempotencyKey()),
    onSuccess: (receipt) => {
      if (receipt.production_id) navigate(`/producoes/${receipt.production_id}`);
    },
    onSettled: () => {
      submitting.current = false;
    },
  });

  useEffect(() => {
    sessionStorage.removeItem(IDEMPOTENCY_KEY);
  }, [payload]);

  useEffect(() => {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    try {
      const draft = JSON.parse(raw) as Record<string, string>;
      setProfileId(draft.profileId ?? "");
      setTopic(draft.topic ?? "");
      setAngle(draft.angle ?? "");
      setTargetMinutes(draft.targetMinutes ?? "25");
      setSources(draft.sources ?? "");
    } catch {
      localStorage.removeItem(DRAFT_KEY);
    }
  }, []);

  function saveDraft() {
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ profileId, topic, angle, targetMinutes, sources }),
    );
    setDraftSaved(true);
  }

  const canStart = preflight.data?.can_start ?? false;

  return (
    <section className={styles.page}>
      <h1>Nova produção</h1>
      <p className={styles.hint}>
        Idioma, voz e formato vêm do perfil. Aqui você informa apenas o pedido.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canStart && !submitting.current) {
            submitting.current = true;
            submit.mutate();
          }
        }}
        className={styles.form}
      >
        <label>
          Canal / perfil
          <input
            value={profileId}
            onChange={(event) => setProfileId(event.target.value)}
            placeholder="Identificador do perfil (opcional)"
          />
        </label>
        <label>
          Tema
          <input
            required
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
          />
        </label>
        <label>
          Recorte (opcional)
          <input value={angle} onChange={(event) => setAngle(event.target.value)} />
        </label>
        <label>
          Duração alvo (minutos)
          <input
            type="number"
            min={1}
            max={120}
            value={targetMinutes}
            onChange={(event) => setTargetMinutes(event.target.value)}
          />
        </label>
        <label>
          Fontes iniciais (uma URL por linha)
          <textarea
            value={sources}
            onChange={(event) => setSources(event.target.value)}
            rows={3}
          />
        </label>

        {topic.trim() && preflight.isPending && <p>Verificando capacidades…</p>}
        {preflight.isError && (
          <InlineError message="Não foi possível verificar as capacidades." />
        )}
        {(preflight.data?.problems ?? []).map((problem) => (
          <p key={problem.code} role="status" className={styles.problem}>
            {problem.message}
          </p>
        ))}
        {preflight.data?.through && (
          <p className={styles.hint}>
            Execução possível até: {preflight.data.through}.
          </p>
        )}

        {submit.isError && (
          <InlineError
            message="Não foi possível iniciar a produção. Tente novamente."
            onRetry={() => submit.mutate()}
          />
        )}
        <div className={styles.actions}>
          <Button
            type="submit"
            loading={submit.isPending}
            disabled={!canStart || submit.isPending}
          >
            Iniciar produção
          </Button>
          <Button variant="secondary" onClick={saveDraft}>
            Salvar rascunho
          </Button>
          {draftSaved && <span role="status">Rascunho salvo, sem execução.</span>}
        </div>
      </form>
    </section>
  );
}
