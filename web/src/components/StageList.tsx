import type { StageName, StageView } from "../api/types";
import { StatusText } from "./StatusText";
import styles from "./StageList.module.css";

const ORDER: StageName[] = [
  "research",
  "script",
  "narration",
  "media",
  "editing",
  "review",
];

const LABELS: Record<StageName, string> = {
  research: "Pesquisa",
  script: "Roteiro",
  narration: "Narração",
  media: "Mídia",
  editing: "Edição",
  review: "Revisão",
};

export function StageList({
  stages,
  selected,
  onSelect,
}: {
  stages: StageView[];
  selected: StageName;
  onSelect: (stage: StageName) => void;
}) {
  const byName = new Map(stages.map((stage) => [stage.name, stage]));

  return (
    <nav aria-label="Etapas da produção" className={styles.list}>
      <ol>
        {ORDER.map((name) => {
          const stage = byName.get(name);
          return (
            <li key={name}>
              <button
                type="button"
                aria-current={selected === name ? "step" : undefined}
                className={selected === name ? styles.selected : undefined}
                onClick={() => onSelect(name)}
              >
                <span>{LABELS[name]}</span>
                <StatusText status={stage?.status ?? "unknown"} />
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
