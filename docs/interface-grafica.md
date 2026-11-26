# Interface gráfica local

Painel local para operar produções sem usar o terminal. O navegador consulta
uma API FastAPI na mesma origem; o processamento continua em Python e as
produções de longa duração rodam em workers independentes da aba.

## Instalação e uso (Windows)

```powershell
python -m uv sync --extra ui
npm.cmd --prefix web ci --no-audit --no-fund
npm.cmd --prefix web run build
python scripts/build_ui.py
ai-video-factory ui --no-browser
```

O comando `ui` valida a porta local, imprime uma URL
`http://127.0.0.1:8787/#token=<segredo>` e troca esse segredo por uma sessão
HttpOnly/SameSite estrita. O token aparece uma única vez e não é gravado em
logs. Se a porta estiver ocupada, escolha outra com `--port`; nenhum processo
alheio é encerrado.

Se os assets compilados não existirem, a API responde com uma página explicando
como gerá-los. Em desenvolvimento, `npm run dev` usa o proxy de `/api` para a
porta 8787.

## O que a interface mostra

- **Produções:** execuções reais do RunStore, com modo `legacy` explícito e
  filtros por canal, estado e texto.
- **Área da produção:** seis estágios observáveis, atividade, artefatos,
  histórico de eventos, memória utilizada e progresso somente quando medido.
  “2 de 6 etapas concluídas” conta etapas, não percentual de tempo.
- **Inspetores:** evidências de pesquisa, fala e direção separadas, narração por
  segmento, licença de mídia, edição no FilmCraft e revisão/pacote. Bundles
  ausentes aparecem como indisponíveis, nunca como conteúdo inventado.
- **Perfis e memória:** revisões versionadas, campos herdados, aprendizados
  observados/inferidos/ativos e suspensão manual opcional. A aplicação
  autônoma de aprendizados não exige aprovação humana.
- **Ferramentas:** estado instalado/configurado sem executar trabalho; o teste
  de conexão só acontece quando o operador clica.
- **Configurações:** tela somente leitura com endereço local, versão da API e
  capacidades reais do ambiente; nenhum campo é alterado nela.

## Recuperação e consistência

- Fechar ou atualizar a aba não encerra o worker. O journal em
  `data/ui/control.sqlite3` guarda jobs, chaves de idempotência e cursores.
- Reconexão SSE usa `Last-Event-ID`; um cursor inválido pede novo snapshot em
  vez de fingir replay completo.
- Duas abas ou retries com a mesma `Idempotency-Key` reaproveitam o mesmo job.
- Um pedido de parada fica “Parada solicitada” até confirmação em ponto seguro;
  uma exportação externa que não aceita cancelamento nunca é declarada
  cancelada.
- Arquivos são resolvidos por ID, com verificação de containment; links para
  fora da raiz são rejeitados. Vídeo/áudio usam `Range`, sem carregar o arquivo
  inteiro em memória.

## Conexão com o plano dos seis estágios

A interface expõe capacidades reais via `GET /api/v1/capabilities`. Enquanto um
serviço de domínio não estiver implementado/configurado, o botão correspondente
aparece desabilitado com o motivo. O pré-flight informa até onde uma produção
pode avançar; ele não inicia modelos, editores ou downloads.

## Tipos e verificação

Os tipos TypeScript em `web/src/api/generated.ts` vêm do OpenAPI da aplicação:

```powershell
cd web
npm run generate:api
npm run typecheck
npm test -- --run
npm run build
```

Back-end:

```powershell
python -m pytest tests/test_ui_*.py -q
```

### Testes de ponta a ponta

```powershell
cd web
npm.cmd run test:e2e
```

O Playwright inicia `scripts/e2e_serve.py`, um servidor somente loopback que
cria artefatos e perfis de teste em um diretório temporário. Os cenários cobrem
abertura do painel, recuperação após atualização, separação de memórias entre
canais e navegação até as configurações.

### Estado observado nesta entrega

- Suíte da interface: 85 testes Python aprovados (um teste de symlink é ignorado
  quando o Windows não concede o privilégio necessário) e 31 testes React
  aprovados.
- Geração de tipos, `typecheck` e `build` concluídos sem erros.
- Os quatro cenários Playwright foram executados contra o servidor controlado
  `scripts/e2e_serve.py`: 4 aprovados. O runner usa um worker porque o bootstrap
  local é de uso único.
- Suíte completa do repositório: 1207 testes passaram, 7 foram ignorados e
  nenhum falhou.
- Nenhum upload/publicação automático foi adicionado.
- Limitações registradas: execução real das etapas depende dos runners do plano
  principal; integração FilmCraft depende de configuração local.
