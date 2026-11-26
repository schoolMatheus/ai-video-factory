import { useQuery } from "@tanstack/react-query";
import { getCapabilities } from "../../api/client";
import type { CapabilitiesView } from "../../api/types";
import { InlineError } from "../../components/InlineError";
import styles from "./SettingsPage.module.css";

type CapabilityKey = Exclude<keyof CapabilitiesView, "api_version">;

const CAPABILITIES: Array<{ key: CapabilityKey; label: string }> = [
  { key: "legacy_read", label: "Leitura de produções legadas" },
  { key: "staged_flow", label: "Fluxo de seis etapas" },
  { key: "profiles", label: "Perfis e memória" },
  { key: "editor", label: "Edição externa" },
  { key: "stop_control", label: "Parada cooperativa" },
  { key: "upload", label: "Upload automático" },
];

export function SettingsPage() {
  const query = useQuery({
    queryKey: ["capabilities"],
    queryFn: getCapabilities,
    retry: false,
  });

  return (
    <section className={styles.page}>
      <h1>Configurações</h1>
      <p className={styles.hint}>
        Valores lidos do painel local. Nenhuma configuração é alterada nesta tela.
      </p>

      {query.isPending && <p>Carregando configuração…</p>}
      {query.isError && (
        <InlineError
          message="Não foi possível carregar a configuração do painel."
          onRetry={() => void query.refetch()}
        />
      )}

      {query.data && (
        <>
          <dl className={styles.facts}>
            <dt>Ambiente</dt>
            <dd>{window.location.origin} · acesso somente local</dd>
            <dt>Versão da API</dt>
            <dd>{query.data.api_version}</dd>
          </dl>

          <h2>Capacidades do ambiente</h2>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Recurso</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {CAPABILITIES.map(({ key, label }) => (
                <tr key={key}>
                  <th scope="row">{label}</th>
                  <td>{query.data[key] ? "Disponível" : "Indisponível"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>Iniciador</h2>
      <p>
        Para abrir o painel local, execute <code>ai-video-factory ui --no-browser</code>.
        A URL de acesso contém um token de uso único.
      </p>
    </section>
  );
}
