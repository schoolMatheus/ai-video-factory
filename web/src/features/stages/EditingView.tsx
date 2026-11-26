import type { ActionAvailability } from "../../api/types";
import { Button } from "../../components/Button";

export function EditingView({
  actions = [],
}: {
  actions?: ActionAvailability[];
}) {
  const open = actions.find((item) => item.action === "open_editor");
  const reconcile = actions.find((item) => item.action === "reconcile_editor");

  return (
    <section aria-label="Edição">
      <h3>FilmCraft</h3>
      <p>Projeto e prévia ainda não disponíveis para esta produção.</p>
      <Button variant="secondary" disabled={!open?.enabled} title={open?.reason ?? undefined}>
        Abrir projeto
      </Button>
      <Button variant="secondary" disabled={!reconcile?.enabled} title={reconcile?.reason ?? undefined}>
        Reconciliar estado
      </Button>
      <p>A exportação bem-sucedida não comprova ausência de mídia offline.</p>
    </section>
  );
}
