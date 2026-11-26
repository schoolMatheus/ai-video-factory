export interface ReviewCheck {
  name: string;
  measured: boolean;
  passed: boolean | null;
}

export function ReviewView({ checks }: { checks?: ReviewCheck[] }) {
  return (
    <section aria-label="Revisão">
      <h3>Verificações e pacote</h3>
      {!checks?.length && <p>Nenhuma verificação medida ainda.</p>}
      {checks?.map((check) => (
        <p key={check.name}>
          {check.name}: {check.measured ? (check.passed ? "passou" : "falhou") : "não medido"}
        </p>
      ))}
      <p>Pacote para publicação ainda não gerado. Nenhum upload é feito automaticamente.</p>
    </section>
  );
}
