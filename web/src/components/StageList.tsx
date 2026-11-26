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

const DEPTH = [styles.depth1, styles.depth2, styles.depth3, styles.depth4];

function planeClass(index: number, selectedIndex: number): string {
  if (index === selectedIndex) return styles.selected;
  if (index < selectedIndex) return styles.done;
  return `${styles.future} ${DEPTH[Math.min(index - selectedIndex, 4) - 1]}`;
}

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
  const selectedIndex = ORDER.indexOf(selected);

  return (
    <nav aria-label="Etapas da produção" className={styles.list}>
      <ol>
        {ORDER.map((name, index) => {
          const stage = byName.get(name);
          const isSelected = selected === name;
          return (
            <li key={name}>
              <button
                type="button"
                aria-current={isSelected ? "step" : undefined}
                className={planeClass(index, selectedIndex)}
                onClick={() => onSelect(name)}
              >
                <span className={styles.mark} aria-hidden="true" />
                <span className={styles.label}>{LABELS[name]}</span>
                <span className={styles.state}>
                  <StatusText status={stage?.status ?? "unknown"} />
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
