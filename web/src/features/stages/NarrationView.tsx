export interface NarrationSegment {
  id: string;
  text: string;
  duration_seconds: number | null;
  content_url: string;
}

export function NarrationView({ segments }: { segments?: NarrationSegment[] }) {
  if (!segments?.length) {
    return <p>Narração ainda não disponível para esta produção.</p>;
  }
  return (
    <section aria-label="Narração">
      <h3>Segmentos</h3>
      <ul>
        {segments.map((segment) => (
          <li key={segment.id}>
            <p>{segment.text}</p>
            {segment.duration_seconds !== null && (
              <p>Duração medida: {segment.duration_seconds}s</p>
            )}
            <audio controls preload="metadata" src={segment.content_url} />
          </li>
        ))}
      </ul>
    </section>
  );
}
