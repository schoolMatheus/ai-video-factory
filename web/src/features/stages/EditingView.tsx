import type { ActionAvailability } from "../../api/types";
import { Button } from "../../components/Button";

export function EditingView({
  actions = [],
  bundle,
  onOpen,
  onReconcile,
}: {
  actions?: ActionAvailability[];
  bundle?: Record<string, unknown> | null;
  onOpen?: () => void;
  onReconcile?: () => void;
}) {
  const open = actions.find((item) => item.action === "open_editor");
  const reconcile = actions.find((item) => item.action === "reconcile_editor");
  const project = typeof bundle?.project_path === "string" ? bundle.project_path : null;
  const previews = Array.isArray(bundle?.previews) ? bundle.previews.length : 0;
  const offline = Array.isArray((bundle?.observed_state as { offline_media?: unknown } | undefined)?.offline_media)
    ? ((bundle?.observed_state as { offline_media: unknown[] }).offline_media.length)
    : 0;

  return (
    <section aria-label="Edição">
      <h3>FilmCraft</h3>
      {project ? (
        <>
          <p>Projeto registrado: {project}</p>
          <p>Prévias registradas: {previews}</p>
        </>
      ) : (
        <p>Projeto e prévia ainda não disponíveis para esta produção.</p>
      )}
      {offline > 0 && <p>{offline} mídia(s) offline no projeto observado.</p>}
      <Button
        variant="secondary"
        disabled={!open?.enabled || !onOpen}
        title={open?.reason ?? undefined}
        onClick={() => onOpen?.()}
      >
        Abrir projeto
      </Button>
      <Button
        variant="secondary"
        disabled={!reconcile?.enabled || !onReconcile}
        title={reconcile?.reason ?? undefined}
        onClick={() => onReconcile?.()}
      >
        Reconciliar estado
      </Button>
      <p>A exportação bem-sucedida não comprova ausência de mídia offline.</p>
    </section>
  );
}
