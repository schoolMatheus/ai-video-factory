export interface Claim {
  text: string;
  evidence: string[];
  contradictions?: string[];
}

export function ResearchView({ claims }: { claims?: Claim[] }) {
  if (!claims?.length) {
    return <p>Dossiê ainda não disponível para esta produção.</p>;
  }
  return (
    <section aria-label="Pesquisa">
      <h3>Afirmações e evidências</h3>
      <ul>
        {claims.map((claim, index) => (
          <li key={`${claim.text}-${index}`}>
            <p>{claim.text}</p>
            <ul>
              {claim.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {(claim.contradictions ?? []).map((item) => (
              <p key={item}>Contradição registrada: {item}</p>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}
