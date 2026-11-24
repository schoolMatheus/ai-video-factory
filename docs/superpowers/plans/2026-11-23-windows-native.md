# Inicialização nativa no Windows

**Goal:** Executar a CLI e o teste real de renderização no Windows, sem WSL.

**Scope:** Compatibilidade da inicialização, travas entre processos, descoberta
de navegador, caminhos de ferramentas/fontes e execução do Remotion. Preservar
as interfaces e o comportamento no Linux. Não implementar o plano editorial
existente nem baixar modelos grandes ou configurar credenciais.

**Approach:** Usar `msvcrt` no Windows e `fcntl` no POSIX; executar a CLI JavaScript
do Remotion com o Node em vez do shim Unix; reconhecer instalações locais de
Chrome/Edge, fontes Windows e executáveis de virtualenv em `Scripts`.

## Entregas e verificação

- [x] Reproduzir a falha de importação e criar testes de regressão para a CLI,
  exclusão entre processos, descoberta do navegador e caminhos nativos.
- [x] Implementar as adaptações sem remover travas ou desativar verificações.
- [x] Instalar dependências Python/Node e acrescentar `tzdata` no Windows.
- [x] Executar testes relevantes, compilação/testes do Remotion e produzir o
  vídeo sintético de três segundos com FFmpeg e navegador locais.
- [x] Documentar os comandos PowerShell e fornecer um iniciador local.

**Acceptance:** `aivideofactory.cmd --help` abre a ajuda; `doctor` responde;
`test-pipeline --json` produz um MP4 real que passa no QC. Produção a partir de
tema continua exigindo modelo de texto, voz e fontes de mídia configurados.

**Known separate limitation:** O caminho avançado de pesquisa em `daily-job`
usa deadlines com `SIGALRM`; não prometer compatibilidade desse comando ao
validar somente o fluxo `video-pipeline` documentado.

**Review:** Revisão independente identificou caminhos relativos resolvidos no
diretório errado após mudar o cwd do subprocesso; corrigido e coberto por
regressão. O wrapper também envia os props por arquivo para evitar o limite de
linha de comando do Windows em roteiros longos. O NumPy, já importado pelo QC,
foi declarado como dependência obrigatória.

**Validation scope:** Testes Python relacionados, novo teste do wrapper e build
TypeScript. O teste sintético real passou no Windows. A suíte preexistente de
schema do Remotion tem três falhas sobre campos desconhecidos, documentadas em
`docs/windows.md`; não foram alterados schema nem esses testes.
