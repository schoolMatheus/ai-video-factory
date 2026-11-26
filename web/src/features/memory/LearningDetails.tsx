import type { MemoryView } from "../../api/types";

export function LearningDetails({ item }: { item: MemoryView }) {
  return (
    <article aria-label={`Aprendizado ${item.id}`}>
      <h3>{item.summary}</h3>
      <p>Estado: {item.state}</p>
      <p>Origem: {item.origin === "explicit" ? "instrução explícita" : item.origin === "inferred" ? "inferência do agente" : "dado observado"}</p>
      {item.condition && <p>Condição: {item.condition}</p>}
      {item.before && <p>Antes: {item.before}</p>}
      {item.after && <p>Depois: {item.after}</p>}
      <ul>
        {(item.evidence ?? []).map((evidence) => (
          <li key={evidence}>{evidence}</li>
        ))}
      </ul>
      {item.revision !== undefined && <p>Revisão: {item.revision}</p>}
    </article>
  );
}
