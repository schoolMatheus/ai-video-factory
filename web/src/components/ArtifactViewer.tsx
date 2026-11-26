import { API_PREFIX } from "../api/types";
import type { ArtifactView } from "../api/types";

export function ArtifactViewer({ artifact }: { artifact: ArtifactView }) {
  const url = `${API_PREFIX}/artifacts/${encodeURIComponent(artifact.id)}/content`;
  const canPreview = artifact.media_type.startsWith("video/");
  const canListen = artifact.media_type.startsWith("audio/");

  return (
    <section aria-label={`Arquivo ${artifact.name}`}>
      <h3>{artifact.name}</h3>
      {canPreview && (
        <video controls preload="metadata" src={url} aria-label={artifact.name} />
      )}
      {canListen && (
        <audio controls preload="metadata" src={url} aria-label={artifact.name} />
      )}
      <a href={url} download={artifact.name}>
        Baixar
      </a>
    </section>
  );
}
