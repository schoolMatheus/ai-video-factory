export interface ReviewCheck {
  name: string;
  measured: boolean;
  passed: boolean | null;
}

export function ReviewView({
  checks,
  bundle,
}: {
  checks?: ReviewCheck[];
  bundle?: Record<string, unknown> | null;
}) {
  const packagePath = typeof bundle?.package_path === "string" ? bundle.package_path : null;
  const failures = Array.isArray(bundle?.failures) ? bundle.failures : [];
  return (
    <section aria-label="Revisão">
      <h3>Verificações e pacote</h3>
      {!checks?.length && <p>Nenhuma verificação medida ainda.</p>}
      {checks?.map((check) => (
        <p key={check.name}>
          {check.name}: {check.measured ? (check.passed ? "passou" : "falhou") : "não medido"}
        </p>
      ))}
      {failures.map((failure, index) => (
        <p key={index}>Falha: {String(failure)}</p>
      ))}
      {packagePath ? (
        <p>Pacote registrado: {packagePath}. Nenhum upload é feito automaticamente.</p>
      ) : (
        <p>Pacote para publicação ainda não gerado. Nenhum upload é feito automaticamente.</p>
      )}
    </section>
  );
}
