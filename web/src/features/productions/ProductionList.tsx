import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { ApiError, listProductions } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { InlineError } from "../../components/InlineError";
import { StatusText } from "../../components/StatusText";
import styles from "./ProductionList.module.css";

export function ProductionList() {
  const [profileId, setProfileId] = useState("");
  const [search, setSearch] = useState("");
  const filters = { profileId, search };
  const query = useQuery({
    queryKey: queryKeys.productions(filters),
    queryFn: () =>
      listProductions({ profile_id: profileId || undefined, search: search || undefined }),
  });

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Produções</h1>
          <p className={styles.subtitle}>
            Acompanhe execuções reais e suas entregas.
          </p>
        </div>
        <Link className={styles.primary} to="/novo">
          Nova produção
        </Link>
      </header>

      <div className={styles.filters}>
        <label>
          Canal
          <input
            value={profileId}
            onChange={(event) => setProfileId(event.target.value)}
            placeholder="Filtrar por canal"
          />
        </label>
        <label>
          Buscar
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tema ou título"
          />
        </label>
      </div>

      {query.isPending && <p>Carregando produções…</p>}
      {query.isError && (
        <InlineError
          message={
            query.error instanceof ApiError
              ? query.error.problem.message
              : "Não foi possível carregar as produções."
          }
          onRetry={() => void query.refetch()}
        />
      )}
      {query.isSuccess && query.data.items.length === 0 && (
        <div className={styles.empty}>
          <p>
            {profileId || search
              ? "Nenhuma produção neste filtro."
              : "Nenhuma produção ainda."}
          </p>
          {profileId || search ? (
            <button
              type="button"
              onClick={() => {
                setProfileId("");
                setSearch("");
              }}
            >
              Limpar filtro
            </button>
          ) : (
            <Link to="/novo">Nova produção</Link>
          )}
        </div>
      )}
      {query.isSuccess && query.data.items.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Tema</th>
              <th>Canal</th>
              <th>Estado</th>
              <th>Início</th>
              <th>Atualização</th>
            </tr>
          </thead>
          <tbody>
            {query.data.items.map((production) => (
              <tr key={production.id}>
                <td>
                  <Link to={`/producoes/${production.id}`}>{production.title}</Link>
                </td>
                <td>{production.profile_id ?? "Legado — sem perfil"}</td>
                <td>
                  <StatusText status={production.state} />
                </td>
                <td>{production.started_at ?? "—"}</td>
                <td>{production.updated_at ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
