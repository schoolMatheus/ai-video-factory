import type { EventView } from "../api/types";
import styles from "./ActivityFeed.module.css";

export function ActivityFeed({ events }: { events: EventView[] }) {
  if (events.length === 0) {
    return <p className={styles.empty}>Nenhuma atividade registrada ainda.</p>;
  }
  return (
    <ol className={styles.feed} aria-label="Histórico de atividade">
      {events.map((event) => (
        <li key={event.id}>
          <time>{event.timestamp ?? "horário não informado"}</time>
          <span>{event.type}</span>
        </li>
      ))}
    </ol>
  );
}
