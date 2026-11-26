export interface MediaShot {
  shot_id: string;
  source: string;
  license: string;
  content_url: string | null;
}

export function MediaView({ shots }: { shots?: MediaShot[] }) {
  if (!shots?.length) {
    return <p>Mídia ainda não disponível para esta produção.</p>;
  }
  return (
    <section aria-label="Mídia">
      <h3>Planos selecionados</h3>
      <ul>
        {shots.map((shot) => (
          <li key={shot.shot_id}>
            <span>{shot.shot_id}</span>
            <span>{shot.source}</span>
            <span>Licença: {shot.license}</span>
            {shot.content_url && (
              <video controls preload="metadata" src={shot.content_url} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
