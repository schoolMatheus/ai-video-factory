export interface ScriptScene {
  scene_id: string;
  spoken: string;
  direction: string;
  sources: string[];
}

/** Plain text only: recovered external content never becomes executable HTML. */
export function ScriptView({ scenes }: { scenes?: ScriptScene[] }) {
  if (!scenes?.length) {
    return <p>Roteiro ainda não disponível para esta produção.</p>;
  }
  return (
    <section aria-label="Roteiro">
      <h3>Fala e direção</h3>
      <table>
        <thead>
          <tr>
            <th>Cena</th>
            <th>Fala</th>
            <th>Direção</th>
            <th>Fontes</th>
          </tr>
        </thead>
        <tbody>
          {scenes.map((scene) => (
            <tr key={scene.scene_id}>
              <td>{scene.scene_id}</td>
              <td>{scene.spoken}</td>
              <td>{scene.direction}</td>
              <td>{scene.sources.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
