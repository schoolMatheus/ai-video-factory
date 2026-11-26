import type { StageStatus } from "../api/types";
import styles from "./StatusText.module.css";

const LABELS: Record<StageStatus, string> = {
  unknown: "Sem informação",
  pending: "Na fila",
  running: "Em execução",
  completed: "Concluído",
  failed: "Falhou",
  superseded: "Substituído",
};

export function StatusText({ status }: { status: StageStatus }) {
  return (
    <span className={`${styles.status} ${styles[status]}`}>
      {LABELS[status]}
    </span>
  );
}
