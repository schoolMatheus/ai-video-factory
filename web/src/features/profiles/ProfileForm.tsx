import { useState } from "react";
import { ApiError, createProfile, reviseProfile } from "../../api/client";
import type { ProfileView } from "../../api/types";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import styles from "./ProfileForm.module.css";

const GROUPS = ["Identidade", "Pesquisa", "Roteiro", "Voz", "Mídia", "Edição", "Revisão"];

export function ProfileForm({ profile }: { profile?: ProfileView }) {
  const [name, setName] = useState(profile?.name ?? "");
  const [language, setLanguage] = useState("pt-BR");
  const [settings, setSettings] = useState(
    JSON.stringify(profile?.settings ?? {}, null, 2),
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ProfileView | null>(null);

  async function save() {
    setError(null);
    try {
      if (profile) {
        setSaved(
          await reviseProfile(profile.id, {
            expected_revision: profile.revision,
            reason: "Alteração pelo painel local",
            settings: JSON.parse(settings) as Record<string, unknown>,
          }),
        );
      } else {
        setSaved(
          await createProfile({
            profile_id: `perfil-${Date.now().toString(36)}`,
            name,
            language,
            niche: "",
          }),
        );
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? "Outra aba ou o agente alterou este perfil. Recarregue antes de salvar."
          : "Não foi possível salvar o perfil.",
      );
    }
  }

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <fieldset>
        <legend>Identidade</legend>
        <label>
          Nome
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          Idioma dos vídeos
          <input value={language} onChange={(event) => setLanguage(event.target.value)} />
        </label>
      </fieldset>
      {GROUPS.slice(1).map((group) => (
        <fieldset key={group}>
          <legend>{group}</legend>
          <p>
            Configurações herdadas e explícitas aparecem abaixo. Valores explícitos
            prevalecem sobre inferências do agente.
          </p>
        </fieldset>
      ))}
      <label>
        Configurações tipadas (JSON)
        <textarea
          rows={6}
          value={settings}
          onChange={(event) => setSettings(event.target.value)}
        />
      </label>
      <p>
        Produções em andamento mantêm o snapshot usado no início; a nova revisão vale
        para as próximas.
      </p>
      <Button type="submit">Salvar perfil</Button>
      {error && <InlineError message={error} />}
      {saved && (
        <p role="status">
          Perfil salvo na revisão {saved.revision}.
        </p>
      )}
    </form>
  );
}
