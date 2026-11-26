import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listEvents, listProductions, listProfiles } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ProductionView } from "../../api/types";
import { InlineError } from "../../components/InlineError";
import { StatusText } from "../../components/StatusText";
import styles from "./Home.module.css";

const SEVERITY: Record<string, string> = {
  info: "informação",
  warning: "aviso",
  error: "erro",
};

function stageCount(production: ProductionView): string | null {
  const observed = (production.stages ?? []).filter(
    (item) => item.observed !== false,
  );
  if (observed.length === 0) return null;
  const completed = observed.filter((item) => item.status === "completed").length;
  return `${completed} de 6 etapas concluídas`;
}

export function Home() {
  const productions = useQuery({
    queryKey: queryKeys.productions({}),
    queryFn: () => listProductions({}),
    retry: false,
  });
  const profiles = useQuery({
    queryKey: queryKeys.profiles(),
    queryFn: listProfiles,
    retry: false,
  });

  const items = productions.data?.items ?? [];
  const running = items.filter((item) => item.state === "running");
  const shown = running.length > 0 ? running : items;
  const featured = running[0] ?? items[0];
  const events = useQuery({
    queryKey: queryKeys.events(featured?.id ?? ""),
    queryFn: () => listEvents(featured?.id ?? ""),
    enabled: Boolean(featured),
    retry: false,
  });

  return (
    <section className={styles.page}>
      <h1>Início</h1>

      <section className={styles.section} aria-label="Em andamento">
        <h2>Em andamento</h2>
        {productions.isPending && <p>Carregando produções…</p>}
        {productions.isError && (
          <InlineError
            message="Não foi possível carregar as produções."
            onRetry={() => void productions.refetch()}
          />
        )}
        {productions.isSuccess && shown.length === 0 && (
          <p className={styles.row}>Nenhuma produção em andamento.</p>
        )}
        {productions.isSuccess && shown.length > 0 && (
          <ul className={styles.list}>
            {shown.map((item) => {
              const count = stageCount(item);
              return (
                <li key={item.id} className={styles.row}>
                  <Link className={styles.titleLink} to={`/producoes/${item.id}`}>
                    {item.title}
                  </Link>
                  <span className={styles.meta}>
                    {item.profile_id ?? "Legado — sem perfil"}
                  </span>
                  <StatusText status={item.state} />
                  {count && <span className={styles.data}>{count}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className={styles.section} aria-label="Atividade recente">
        <h2>Atividade recente</h2>
        {featured && events.isPending && <p>Carregando atividade…</p>}
        {featured && events.isError && (
          <InlineError
            message="Não foi possível carregar a atividade."
            onRetry={() => void events.refetch()}
          />
        )}
        {productions.isSuccess &&
          (!featured || (events.isSuccess && events.data.items.length === 0)) && (
            <p className={styles.row}>Nenhuma atividade registrada.</p>
          )}
        {featured && events.data && events.data.items.length > 0 && (
          <ul className={styles.list}>
            {events.data.items
              .slice(-6)
              .reverse()
              .map((event) => (
                <li key={event.id} className={styles.row}>
                  <span>{event.type}</span>
                  <span className={styles.meta}>
                    {SEVERITY[event.severity] ?? event.severity}
                  </span>
                  <time className={styles.data}>
                    {event.timestamp ?? "horário não informado"}
                  </time>
                </li>
              ))}
          </ul>
        )}
      </section>

      <section className={styles.section} aria-label="Nichos cadastrados">
        <h2>Nichos cadastrados</h2>
        {profiles.isPending && <p>Carregando perfis…</p>}
        {profiles.isError && (
          <InlineError
            message="Não foi possível carregar os perfis."
            onRetry={() => void profiles.refetch()}
          />
        )}
        {profiles.isSuccess && profiles.data.items.length === 0 && (
          <p className={styles.row}>
            Nenhum nicho cadastrado. <Link to="/perfis">Cadastrar perfil</Link>
          </p>
        )}
        {profiles.isSuccess && profiles.data.items.length > 0 && (
          <ul className={styles.list}>
            {profiles.data.items.map((profile) => (
              <li key={profile.id} className={styles.row}>
                <Link className={styles.titleLink} to="/perfis">
                  {profile.name}
                </Link>
                <span className={styles.data}>{profile.niche || "sem nicho"}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section} aria-label="Notícias dos nichos">
        <h2>Notícias dos nichos</h2>
        <p className={styles.reserved}>
          Sem fonte conectada. Espaço reservado para notícias dos nichos.
        </p>
      </section>
    </section>
  );
}
