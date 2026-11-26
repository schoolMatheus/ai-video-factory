import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getProfile, listProfiles } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { InlineError } from "../../components/InlineError";
import { ProfileForm } from "./ProfileForm";
import styles from "./ProfileList.module.css";

export function ProfileList() {
  const list = useQuery({ queryKey: queryKeys.profiles(), queryFn: listProfiles, retry: false });
  const selectedId = new URLSearchParams(window.location.search).get("perfil");
  const selected = useQuery({
    queryKey: ["profile", selectedId],
    queryFn: () => getProfile(selectedId ?? ""),
    enabled: Boolean(selectedId),
    retry: false,
  });

  return (
    <section className={styles.page}>
      <h1>Perfis</h1>
      {list.isPending && <p>Carregando perfis…</p>}
      {list.isError && (
        <InlineError
          message="Perfis ainda não disponíveis neste ambiente."
          onRetry={() => void list.refetch()}
        />
      )}
      {list.isSuccess && (
        <table>
          <thead>
            <tr>
              <th>Canal</th>
              <th>Revisão</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {list.data.items.map((profile) => (
              <tr key={profile.id}>
                <td>{profile.name}</td>
                <td>{profile.revision}</td>
                <td>
                  <Link to={`/perfis?perfil=${encodeURIComponent(profile.id)}`}>Editar</Link>
                  {" · "}
                  <Link to={`/memoria?perfil=${encodeURIComponent(profile.id)}`}>Memória</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {list.isSuccess && list.data.items.length === 0 && (
        <p>Nenhum perfil cadastrado neste ambiente.</p>
      )}
      {selected.data && <ProfileForm profile={selected.data} />}
      {!selectedId && <ProfileForm />}
    </section>
  );
}
