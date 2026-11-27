# AI Video Factory — Auditoria, correções e continuidade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para executar as tarefas em ordem, com teste de regressão antes de cada correção. Delegação depende do método escolhido para a execução. Os checkboxes deste documento permanecem abertos até a verificação da entrega correspondente.

**Goal:** Conectar e corrigir o que já foi implementado para que o fluxo de produção, a memória autônoma e a interface cumpram os contratos dos planos originais em uma jornada operacional verificável.

**Architecture:** Preservar os módulos Python, os contratos versionados, SQLite, RunStore e o frontend React existentes. Corrigir os composition roots, as fronteiras de estado e as integrações, substituindo confirmações sem efeito e caminhos exclusivos de teste por serviços produtivos observáveis. A interface e a CLI devem usar os mesmos serviços de produção, perfil e aprendizagem.

**Tech Stack:** Python 3.12, Pydantic, Typer, FastAPI, SQLite, MCP/FilmCraft, TypeScript/React, Vite, TanStack Query, pytest, Vitest e Playwright já adotados pelo projeto.

**Spec:** [Plano de estágios, perfis e memória](2026-11-23-canal-dark-estagios-memoria-filmcraft.md), [plano da interface gráfica](2026-11-23-interface-grafica.md) e achados comprovados nas seções 1–7 deste documento.

**Data da auditoria:** 26 de novembro de 2026.

**Estado:** Diagnóstico e plano de correção. A criação deste arquivo não altera a aplicação nem executa as correções.

## Global Constraints

- Não reescrever a aplicação nem repetir funcionalidades já entregues apenas para corresponder à organização textual dos planos anteriores.
- Preservar as decisões do usuário: seis estágios, vídeos horizontais longos, FilmCraft via MCP e memória autônoma separada por canal.
- Autonomia continua autorizada: não introduzir aprovação humana obrigatória por aprendizado. Exigir evidência e avaliação reais não significa exigir aprovação do operador.
- A aprovação de publicação continua separada e não é removida nesta atualização.
- Não tratar classes existentes, arquivos presentes ou testes com doubles como comprovação de uma jornada produtiva completa.
- Não usar porcentagem de conformidade sem uma matriz explícita de requisitos; os status deste relatório são qualitativos e possuem evidência.
- Dar precedência às correções de integridade, execução e isolamento antes de acrescentar novas telas ou polimento.
- Usar o estado atual do workspace: houve commits de nicho/perfis durante a auditoria. Não desfazer essas alterações nem registrar ausência de nicho como pendência.
- As referências de linha são do código lido nesta auditoria; conferir os símbolos novamente antes de editar, pois outras frentes podem continuar trabalhando.
- Não baixar modelos, gastar créditos, produzir vídeo longo ou modificar uma instalação do FilmCraft automaticamente durante a auditoria.
- Pesos finos, calibração estética, analytics, headless/lote e escolha definitiva de nicho/voz continuam legitimamente adiados.

## Review Focus

1. API aceita produção, mas ela precisa existir imediatamente na consulta e chegar a um resultado real. Cobertura: C03, C04 e C13.
2. Revisão reprovada não pode terminar com estado externo de sucesso, e revisão aprovada precisa registrar seu pacote sem violar a raiz de integridade. Cobertura: C01.
3. Perfil/configuração/memória precisam alterar o comportamento real do runner, mantendo isolamento e preferências explícitas. Cobertura: C02, C09, C10 e C11.
4. Dois episódios com os mesmos IDs locais de cena não podem reutilizar o projeto ou os clipes um do outro. Cobertura: C07.
5. Testes de navegador precisam atravessar UI → API → worker → serviços, em vez de validar somente um botão habilitado ou respostas simuladas. Cobertura: C13.

---

## 1. Conclusão executiva

**O projeto evoluiu substancialmente, mas não está integralmente conforme os dois planos.** Há implementação real de estrutura, persistência, contratos, testes, painel e componentes de integração. Permanecem lacunas funcionais que impedem uma produção completa e confiável pelas entradas operacionais.

O principal problema não é falta de telas ou nomes de módulos. É a desconexão entre partes que, isoladamente, possuem testes: o worker padrão da UI não executa o coordenador; a CLI não injeta descoberta/pesquisa produtiva; a aprendizagem não é ligada ao caminho padrão; várias ações retornam aceitação sem executar; a edição descarta faixas planejadas; a revisão não governa corretamente o resultado final.

Além disso, foram reproduzidos defeitos na aplicação e reversão de configurações aprendidas. Portanto, não é adequado declarar a memória autônoma ou a produção de ponta a ponta prontas apenas pelos testes unitários existentes.

### Escopo e revisões observadas

- Checkout local: `schoolMatheus/ai-video-factory`.
- Revisão no início: `45fe05c` — polimento do design system e painel na porta 8787.
- Durante a auditoria entraram `5863177`, `c8b17f6` e `98fc1bb`, relativos ao plano da home e ao nicho de perfis. A área de perfis foi relida depois dessas mudanças.
- Revisão de fechamento: `718ca2e`, após `4942dc3`, com a home ligada à rota inicial e a lista em `/producoes`. O frontend foi testado novamente depois dessa ligação; a home não é registrada como recurso ausente.
- Nenhuma correção de código da aplicação foi aplicada nesta auditoria.
- Foram lidos os dois planos, código operacional e testes; executados testes existentes, build e reproduções determinísticas sem modelos/rede/editor.
- Compatibilidade real com uma instalação de FilmCraft, qualidade da voz e piloto de 20–30 minutos continuam sem comprovação nesta auditoria.

## 2. O que já está implementado e deve ser aproveitado

| Área | Implementação real aproveitável | Limite observado |
|---|---|---|
| Windows | Adaptadores de caminhos/fontes, lock de arquivo e iniciador local | Não prova todos os caminhos avançados ou integrações externas |
| Contratos | Bundles de pesquisa, roteiro, narração, mídia, edição e revisão | Contratos não estão inteiramente materializados pelas entradas padrão |
| Coordenador | Sequenciamento, manifests, fingerprints, artefatos e resultados | Revisão/erros, invalidação e aprendizagem têm lacunas de integração |
| Perfis | SQLite, revisões, revisão esperada, snapshots históricos e backup | Resolução de configurações, reconstrução e reversão precisam correção |
| Observações | Registro por perfil, produção e estágio; event_key | Algumas colisões/atualizações e tentativas quebram semântica/isolamento |
| Mídia | Provedores e registro de direitos; memória por canal | O adaptador produtivo pode usar URL como nome de arquivo no Windows |
| FilmCraft | Cliente MCP, abstração de capabilities, timeout e testes com editor controlado | Montagem incompleta e compatibilidade com editor real não validada |
| UI local | React, design system, navegação, lista legada, sessão e CSRF | Operações do fluxo novo e inspetores não estão ligados de ponta a ponta |
| Arquivos | Resolução por ID, containment e streaming Range | Inspeção por bundle e pacote editável ainda incompletos |
| Configurações | Tela real somente leitura, diagnóstico de instalação/configuração | Capabilities ainda confundem módulo instalado com serviço operacional |
| Home e nichos | Home inicial com produções/atividade/perfis; cadastro e leitura do nicho; notícias como espaço reservado explícito | Acompanhamento herda as limitações dos dados/eventos do backend; não há fonte de notícias conectada, conforme seu escopo |
| Testes | Suítes Python/React e quatro cenários de navegador | A cobertura atual aceita vários caminhos simulados/desconectados |

## 3. Verificação realizada

### Comandos e resultados

| Verificação | Resultado desta auditoria | O que comprova |
|---|---|---|
| `npm.cmd test -- --run --reporter=dot` em `web/` | 37 testes aprovados, 10 arquivos, na verificação final | Componentes, home e clientes nos cenários unitários existentes |
| `npm.cmd run typecheck` em `web/` | Aprovado na verificação final | Consistência estática do frontend nessa revisão |
| `npm.cmd run build` em `web/` | Aprovado; Vite compilou 130 módulos | Frontend compila para distribuição |
| `npm.cmd run test:e2e` em `web/` | 4 cenários aprovados | Abertura/preflight, refresh legado, separação simples de memória e configurações |
| Suíte Python completa com `--durations=10` | Interrompida após aproximadamente 11 minutos, durante renderizações longas dos testes legados com FFmpeg | Não há resultado global desta tentativa; não declarar a suíte completa aprovada |
| Suíte Python com três arquivos demorados excluídos | 1.180 aprovados, 6 ignorados, em 96,55 s | Regressões da ampla camada restante, incluindo os módulos novos |
| Suíte direcionada dos módulos novos | 162 aprovados, 1 ignorado, em 40 s | Checagem adicional do escopo de perfis/estágios/workflow/UI; esses testes se sobrepõem à rodada de 1.180 e não devem ser somados |

A rodada ampla usou exatamente:

```powershell
.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_daily_job.py --ignore=tests/test_production.py --ignore=tests/test_remotion_pixel_integration.py --durations=10
```

Os três arquivos excluídos não foram considerados aprovados. Sua validação integral e o piloto externo permanecem pendentes; não houve falha global comprovada nem aprovação global inferida a partir da tentativa interrompida.

Warnings de depreciação do ambiente de testes foram observados, mas não foram confundidos com os defeitos operacionais abaixo.

Os quatro E2E não iniciam e concluem um episódio: o teste de produção preenche tema e verifica botão habilitado; o de recuperação recarrega um manifest legado. O teste Python de duas abas substitui o spawn do worker. Isso explica como as suítes podem passar sem comprovar as jornadas prometidas.

### Reproduções independentes

Executadas com diretórios temporários, dados de teste e serviços injetáveis; nenhuma chamada de modelo, provedor remoto ou editor real foi necessária.

| Caso | Saída/efeito observado |
|---|---|
| Preflight sem perfil e sem runners produtivos | `can_start=true`, etapa final `review`, sem pendência |
| Criar produção e chamar o executor padrão real | Job aceito como queued, depois `DependencyUnavailableError` e job failed |
| Consultar a produção cujo job foi aceito | 404: o receipt não criou uma produção consultável |
| Solicitar ação resume sobre execução existente | Receipt queued; consultar o job devolvido resulta em 404 |
| Criar primeiro perfil com dados vazios e adapter padrão | HTTP 503, apesar da capacidade de perfis anunciada |
| Dois PATCH de perfil com a mesma revisão e adapter real | Primeiro HTTP 200; segundo HTTP 500, em vez do conflito 409 previsto |
| Pesquisar tema pela composição padrão da CLI | `ResearchStageError`: nenhuma fonte inicial ou descoberta |
| Ler configuração explícita `narration.voice` em formato flat | O accessor retorna FALLBACK em vez do valor escolhido |
| Candidato de mídia com URL como identidade | Nome de arquivo inválido no Windows |
| Plano contendo voz enviado ao editor controlado | Apenas inserção de vídeo é enviada |
| Cinco cenas padrão com voz de 10 s e pausas | Narração total de 51,5 s versus fim visual de 53,4 s |
| ReviewStage real reprovando entradas | Bundle failed, mas produção externa completed e sem falhas |
| ReviewStage real aprovando e gerando pacote | RunStore rejeita `package/review_manifest.json` fora da raiz de artefatos |
| Substituir regra de música depois de outra regra | Regra nova ativa, mas valor antigo pode continuar efetivo |
| Suspender regra após revisão explícita independente | Configuração explícita posterior pode desaparecer |
| Candidato com evento existente, sem artefato ou ensaio | Aprendizado ativado pelo fallback sem avaliador |
| Regra incompatível com versão da ferramenta | ID some da lista, mas seu valor continua nas configurações |
| Mesmo snapshot recebe nova observação posterior | Digest de memória muda e compromete estabilidade da retomada |
| Reutilizar candidate_id de A em B | Consulta de A pode retornar payload pertencente a B |

As falhas são de ligação ou integridade demonstrável, não apenas falta de credenciais/modelos no ambiente.

## 4. Matriz resumida de conformidade dos planos

Legenda: **parcial** = implementação existe, mas um requisito operacional foi refutado; **base entregue** = infraestrutura presente, ainda não suficiente para o piloto; **pendente de validação** = depende de ensaio real não realizado; **adiado** = fora do escopo inicial conforme decisão anterior.

| Requisito do plano principal | Estado | Continuidade |
|---|---|---|
| T1 — Plataforma Windows | Base entregue | Preservar; validar novos adaptadores e paths reais |
| T2 — Contratos versionados | Base entregue | Usar nos testes cruzados e nas APIs |
| T3–T5 — Perfis, observações e contexto | Parcial | C02, C09 e C11 |
| T6 — Coordenação/retomada/invalidação | Parcial | C01, C03 e C04 |
| T7 — Pesquisa profunda sobre tema | Parcial | C05 |
| T8 — Roteiro editorial completo | Parcial | C05 |
| T9 — Narração real/idioma | Parcial + validação externa | C02, C06 e C13 |
| T10 — Mídia por plano/direitos | Parcial | C06 |
| T11–T12 — FilmCraft e montagem completa | Parcial + validação externa | C07 e C13 |
| T13 — Revisão e pacote completo | Parcial | C01 e C08 |
| T14 — Aprendizagem operacional autônoma | Parcial | C09 e C10 |
| T15 — Entradas CLI operacionais | Parcial | C03 e C05 |
| T16 — Piloto real e migração | Pendente de validação | C13; revisar alegações documentais |

| Requisito do plano da interface | Estado | Continuidade |
|---|---|---|
| UI-1 — Consulta/legado | Base entregue | Acrescentar agregação do modo staged em C04 |
| UI-2 — API/sessão | Base entregue, capacidades parciais | C03 e C11 |
| UI-3 — SSE/reconexão | Parcial | C04 |
| UI-4 — Workers duráveis e ações | Parcial | C03 |
| UI-5 — Shell/tokens/contratos | Base entregue | Preservar; atualizar DTOs sem perder tipos gerados |
| UI-6–UI-7 — Criação e acompanhamento | Parcial | C03 e C04 |
| UI-8–UI-9 — Inspetores/editor/revisão | Parcial | C08 e C12 |
| UI-10 — Perfis/memória | Parcial | C11 |
| UI-11 — Launcher/distribuição | Base entregue, primeiro perfil bloqueado | C11 e C13 |
| UI-12 — Jornada real e recuperação | Parcial | C13 |
| Tela extra de configurações | Entregue como somente leitura | Não exigir edição de configurações que não foi prometida |
| Home, rota inicial e nicho do perfil | Base entregue e revalidada no fechamento | Preservar; corrigir as projeções/eventos compartilhados com o restante da aplicação |
| Analytics, headless/lote e calibração fina | Adiado | Não incluir como defeitos obrigatórios deste plano |

## 5. Achados prioritários com evidência

Os caminhos abaixo são relativos à raiz do repositório. Prioridade P1 indica bloqueio de jornada ou integridade; P2 indica comportamento incorreto que deve ser resolvido para fechar a entrega. Não houve achado que justificasse declarar uma emergência P0.

### A01 — P1 — Produção gráfica aceita, mas executor padrão não implementado

`ui_backend/domain.py:33–50` usa presença do módulo como capacidade. `ui_backend/routes.py:116–178` permite preflight/submissão sem perfil válido. `ui_backend/jobs.py:299–303` sempre levanta `DependencyUnavailableError`; `worker.py:57–59` usa esse executor. Não existe chamada operacional até `run_production` por esse caminho.

O receipt é devolvido antes de uma produção aparecer nos read models, resultando em 404 na navegação. O contrato de `run_default_executor(job_id, payload)` também não expressa corretamente a fronteira esperada por `execute_job`, que chama o executor com payload/control; isso precisa ser unificado, não apenas trocar o corpo do stub.

### A02 — P1 — Ações confirmadas sem efeito e fila incompleta

`ui_backend/routes.py:349–363` chama `domain.execute_action`, que apenas devolve objetos (`domain.py:103–160`). O receipt usa `production_id` como `job_id` inexistente. Botões de retomada/editor ainda não possuem handlers operacionais no workspace e inspetor.

`jobs.py:84–86` grava chave de idempotência e job separadamente. `worker.py:57` faz claim de ID específico, que não usa a restrição de uma produção ativa de `next_queued_job`. Não há composição operacional de reconciliação periódica/heartbeat para jobs reais. Retomar, parar, revisar texto e substituir mídia precisam efeitos persistidos verificáveis.

### A03 — P1 — A GUI não agrega produções novas nem recebe corretamente eventos vivos

`ui_backend/read_models.py:108–139,291–348` lê manifests da raiz legada e os projeta individualmente como `legacy`. A aplicação em `app.py:88–94` aponta para `state/` e `runs/`, enquanto o novo coordenador persiste em `data/projects/<perfil>/<produção>/state` e `artifacts`.

`routes.py:339` emite SSE nomeado; `web/src/api/events.ts:39–54` escuta `onmessage`, mas não os nomes de produção/estágio. O cursor guardado não é enviado na nova conexão (`events.ts:28–32,89–90`). O workspace acrescenta histórico, mas não aplica/invalida snapshot por evento normal. Existem ainda formatos diferentes de cursor entre snapshot, histórico e replay.

### A04 — P1 — Representação de configurações incompatível entre perfil e runners

`config/profile.example.json`, `profiles/context.py` e patches usam chaves flat, como `narration.voice`. `workflow/contracts.py:46–53` percorre objetos aninhados e devolve defaults. Narração, mídia, revisão e modo de edição são afetados; `workflow/planning.py:32–36` lê flat diretamente, criando divergência entre montagem e revisão.

Uma configuração exibida no perfil ou no relatório não comprova que ela foi aplicada ao software. O teste deve observar os parâmetros e o resultado do provedor real/adaptado.

### A05 — P1 — Pesquisa e roteiro padrão não entregam o fluxo editorial prometido

`workflow_cli.py:78,102` instancia `ResearchStage()` sem descoberta e fixa seeds vazias; não há flag operacional para fornecê-las. `stages/research.py:61,68,166` falha sem fontes ou usa modo não produtivo quando os transportes não foram injetados. A existência do pipeline de pesquisa mais rigoroso não basta sem sua composição na entrada usada pelo operador.

`stages/script.py:74–125` transforma cada claim em uma frase/cena e dois planos genéricos, sem usar gerador LLM por padrão, alvo de duração, nicho e direção aprendida. Usa todas as claims e apenas verifica referência de ID, sem garantir tratamento editorial da evidência/contradição.

### A06 — P1 — Mídia real quebra por URL como nome local e TTS aceita degradação indevida

`workflow_cli.py:59` usa URL como identidade; `stages/media.py:107` a transforma diretamente em filename. Esse caminho foi reproduzido com erro no Windows.

`stages/narration.py:44–48` constrói o provedor local padrão; `integrations/tts.py:98–104` registra fallback efetivo, mas não bloqueia mudança de engine/idioma inadequada. A função legada pode cair para espeak em inglês quando modelos não existem. Idiomas declarados no perfil não equivalem a capacidades verificadas do software instalado.

### A07 — P1 — Edição incompleta, tempos divergentes e projeto sem identidade de episódio

`stages/editing.py:82–84` ignora tracks que não sejam vídeo, apesar de `workflow/planning.py:88–94` produzir faixas de voz e texto. A narração não é materializada na edição.

`planning.py:41,50,86` associa tempo do áudio apenas ao primeiro plano e usa fallback para outros; pausas não governam toda a distribuição visual. A reprodução com cinco cenas demonstra drift.

`editing.py:68,86–87` inspeciona o projeto aberto e reutiliza qualquer shot_id, sem verificar produção, arquivo, tempos ou digest. IDs padrão se repetem entre episódios, permitindo reaproveitamento indevido ou ignorar uma mídia corrigida.

### A08 — P1 — Revisão falha vira sucesso; revisão aprovada quebra a integridade

`stages/review.py:159,171` produz bundle failed, mas devolve `StageResult` com default completed. `workflow/orchestrator.py:231,258` completa a execução e não consome as falhas/reroutes. A reprodução comprova sucesso externo com reprovação interna.

No caminho aprovado, `review.py:136,168–169` declara `package/review_manifest.json` fora da raiz `<produção>/artifacts` usada pelo coordenador (`orchestrator.py:113`). `run_store.py:391–395` rejeita o caminho; a exceção pós-runner não é convertida em erro estruturado.

### A09 — P1 — QC e pacote final não completam os requisitos de entrega

`review.py:92–110` não compara duração ao alvo solicitado nem comprova evidência factual apenas por verificar IDs. Em `:129`, lacunas com estratégia textual “compor plano” são desconsideradas, sem composição efetivamente produzida.

`review.py:137–145` não fornece thumbnail, capítulos ou legendas ao empacotador, nem inclui o projeto FilmCraft e suas dependências para recuperação. `editing.py:248–252` guarda caminho textual do projeto e prévias vazias. A ausência desses arquivos não deve ser confundida com decisão editorial de não usá-los.

### A10 — P1 — Aprendizagem não ligada à operação e avaliação permissiva

`workflow_cli.py:129–131,157` não passa revisor/avaliador; `workflow/orchestrator.py:245` só aprende quando um revisor é fornecido. Feedback apenas grava observação. O revisor padrão espera um `proposed_patch` já pronto, que os runners não geram.

Mesmo quando chamado, `profiles/learning.py:101–118,157–163` aceita existência de um event_key como evidência e pode ativar sem ensaio/artefato. `store.py:564–578` verifica resultado pass, mas não garante todos os requisitos da política, checks, evidências e versão imutável do candidato no ponto transacional de ativação.

### A11 — P1 — Reconstrução/reversão e compatibilidade de aprendizados incorretas

`profiles/store.py:776–782` e `profiles/context.py:99–103` reaplicam snapshots inteiros, fazendo uma regra de outro campo restaurar um valor antigo. `store.py:674` usa revisão anterior à suspensão como se fosse a base anterior à ativação, podendo apagar preferências explícitas recentes.

`context.py:91–103` filtra regra incompatível, mas parte de settings já materializadas com o patch. O efeito continua mesmo sem ID ativo. Condições de aplicação não são avaliadas efetivamente.

### A12 — P2 — Snapshot, escopo e orçamento não garantem retomada estável

`profiles/context.py:109–136` lê observações atuais e inclui a revisão global no digest. `orchestrator.py:166` também inclui a revisão global nos fingerprints. Isso altera o contexto antigo com observações futuras e prejudica invalidação seletiva.

`profiles/store.py:454–459` aceita colisão de candidate_id com payload de outro perfil, mantendo o proprietário da linha. Getters de candidatos/avaliações também permitem escopo omitido. `orchestrator.py:151,350` fixa tentativa 1 e a chave de falha colapsa retentativas.

O orçamento conta uma unidade por estágio externo e reinicia na chamada seguinte; não limita todas as operações reais, tempo, tentativas ou avaliações. É defeito funcional de orçamento, não calibração estética adiada.

### A13 — P1/P2 — Perfis e memória na UI ainda têm falhas de persistência e isolamento

Após as mudanças de nicho, continuam observáveis: estado de formulário inicializado apenas na montagem (`ProfileForm.tsx:11–16`), reutilização sem key (`ProfileList.tsx:56`) e salvamento com novas props/estado antigo (`ProfileForm.tsx:25–28`). O cenário relevante é alternar perfis já presentes no cache.

Nome/idioma editados não entram no PATCH; settings da criação não entram no POST; salvar não atualiza revisão/cache; nome real não é projetado do registro persistido. `profile_adapter.py:63–77` não traduz RevisionConflict/NotFound para os erros HTTP previstos.

Uma instalação limpa não recebe adaptador de perfis porque `ui_cli.py:57,62` só passa profiles_db se o arquivo já existe. A memória envia/projeta revisão 1, feedback fixo e não inclui candidatos/avaliações/condições completas. Nicho na criação e projeção foi corrigido durante a auditoria e não integra esta lista de ausência.

### A14 — P2 — Inspetores e ações de tela não recebem dados/handlers reais

`ProductionWorkspace.tsx:72–79` instancia ResearchView, ScriptView, NarrationView e MediaView sem suas entregas; revisão e edição permanecem parcialmente em placeholders. O botão Retomar e ações de editor não possuem callbacks produtivos. O retry do erro de estágio usa uma função vazia.

Os componentes podem passar testes isolados recebendo props que o workspace nunca fornece. Cobrir o componente pai com um backend real de teste é necessário para fechar essa fronteira.

## 6. O que não é pendência obrigatória desta correção

- Escolher agora o nicho definitivo, voz, trilha, duração exata de cada plano ou pesos de qualidade.
- Tornar a tela de configurações editável: sua entrega adicional foi explicitamente somente leitura.
- Analytics/CTR/retenção, distribuição remota, múltiplas máquinas, headless/lote e agendamento automático.
- Declarar defeito de FilmCraft/LLM por uma credencial ou modelo não estar instalado. Isso é diagnóstico de configuração; diferente das falhas de ligação comprovadas acima.
- Acrescentar novas funcionalidades à home: sua ligação de rotas e os testes entraram durante a auditoria e foram revalidados. Corrigir o backend que ela consome é parte das tarefas abaixo; criar um serviço de notícias não é.

## 7. Estratégia de correção

1. **Estado honesto primeiro:** corrigir sucesso falso, preflight e receitas de ações inexistentes.
2. **Uma composição produtiva compartilhada:** CLI e worker usam a mesma fábrica de serviços, configurações e limites.
3. **Uma produção consultável:** agregação por produção, leitura staged e contrato único de eventos/cursor.
4. **Conteúdo e montagem reais:** pesquisa/roteiro produtivos, mídia/voz efetivas e todas as faixas enviadas ao editor.
5. **Memória correta antes de ativá-la por padrão:** corrigir patches, base, isolamento, compatibilidade e evidência; depois ligar revisor/avaliadores à operação.
6. **Interface sobre o domínio corrigido:** handlers, inspetores e formulários com testes cruzados.
7. **Aceitação por jornada:** não encerrar com apenas os testes existentes passando.

## 8. Tarefas de correção e continuidade

Cada tarefa exige teste que reproduz o achado antes da correção, implementação mínima, verificação do comportamento e regressões pertinentes. Não alterar asserções para manter um falso sucesso nem trocar o serviço real por um fake que exclua a fronteira defeituosa.

### C01 — Estado final, erro estruturado e raiz do pacote

**Prioridade:** P1. **Achados:** A08.

**Arquivos:** `stages/review.py`, `workflow/orchestrator.py`, `workflow/models.py`, `run_store.py` somente se necessário; `tests/test_stage_review.py`, `tests/test_staged_workflow.py` e novo `tests/test_review_workflow_integration.py`.

**Contrato:** revisão reprovada gera resultado de produção não aprovado com falhas/reroutes; pacote aprovado é artefato contido na raiz autorizada, com referência externa de distribuição somente se explicitamente modelada.

- [ ] Criar `test_real_review_failure_cannot_complete_production` com ReviewStage/RunStore reais e predecessores determinísticos.
- [ ] Criar `test_real_review_package_is_contained_and_registered`, reproduzindo o erro de `package/review_manifest.json`.
- [ ] Executar os testes e confirmar as falhas originais.
- [ ] Propagar reprovação e tratar erros de persistência/validação pós-runner; salvar bundle/diagnóstico mesmo na falha.
- [ ] Decidir um único local canônico para pacote dentro de artefatos e adaptar consultas/empacotamento sem afrouxar containment.
- [ ] Testar CLI com exit code não zero na reprovação e pacote íntegro no caso aprovado.
- [ ] Verificar `python -m pytest tests/test_review_workflow_integration.py tests/test_stage_review.py tests/test_staged_workflow.py -q`.

**Aceitação:** nenhum sucesso externo com revisão falha; caminho aprovado alcança registro de pacote real.

### C02 — Representação única de configurações e parâmetros efetivos

**Prioridade:** P1. **Achados:** A04.

**Arquivos:** `workflow/contracts.py`, `profiles/context.py`, `profiles/models.py`, `workflow/planning.py`, runners consumidores e `config/profile.example.json`; novo `tests/test_effective_stage_settings.py`.

**Contrato:** manter chaves flat já usadas pelos perfis ou migrá-las explicitamente; todos os leitores usam a mesma representação e rejeitam formatos mistos ambíguos.

- [ ] Criar `test_explicit_voice_reaches_tts_provider`, verificando SpeechRequest efetivamente recebido, não somente effective_config.
- [ ] Testar idiomas, candidatos de mídia, modo de edição, resolução e política de revisão através dos runners reais.
- [ ] Implementar accessor/resolvedor único e migração determinística se necessária.
- [ ] Testar preferências explícitas, overrides e aprendizado aplicável preservando precedência.
- [ ] Verificar que montagem e revisão concordam sobre os mesmos valores.
- [ ] Executar `python -m pytest tests/test_effective_stage_settings.py tests/test_memory_context.py tests/test_stage_narration.py tests/test_assembly_plan.py -q`.

**Aceitação:** o valor escolhido no perfil produz efeito no serviço e no artefato final.

### C03 — Composição produtiva e jobs/ações persistentes

**Prioridade:** P1. **Achados:** A01 e A02.

**Arquivos:** `workflow_cli.py`, novo `workflow/services.py`, `ui_backend/domain.py`, `jobs.py`, `worker.py`, `control_store.py`, `routes.py`; novo `tests/test_ui_operational_workflow.py`.

**Interfaces novas:** `build_production_services(snapshot, paths, transports) -> ProductionServices`; `execute_production_job(payload, control, services) -> ProductionResult`. `ProductionServices` agrupa runners, aprendizado e configuração, sem segredos serializados. Manter a assinatura `executor(payload, control)` em todas as chamadas do worker.

- [ ] Testar a submissão HTTP com composição padrão e fronteiras HTTP/LLM/TTS/editor controladas, sem substituir o worker por um retorno constante.
- [ ] Criar `test_receipt_has_queryable_job_and_production_before_worker_starts`.
- [ ] Implementar criação transacional de idempotência/job e identidade de produção persistida antes do receipt.
- [ ] Substituir stub do executor por chamada real ao coordenador com caminhos/perfil/orçamento resolvidos.
- [ ] Fazer cada action criar job real ou executar operação síncrona explicitamente confirmada; action indisponível deve falhar, não devolver queued fictício.
- [ ] Implementar claim exclusivo da fila pelo caminho usado por worker.main, despacho após conclusão, heartbeat e reconciliação no startup.
- [ ] Conectar parada cooperativa pelo `control` no coordenador e pontos seguros, sem matar editor arbitrariamente.
- [ ] Testar duas submissões diferentes, crash entre persistência e spawn, timeout de ação externa, duas abas e restart da API.
- [ ] Executar `python -m pytest tests/test_ui_operational_workflow.py tests/test_ui_jobs.py tests/test_ui_worker.py -q`.

**Aceitação:** um clique aceito cria recurso consultável e executa/encerra um trabalho real; nenhum receipt aponta para job inexistente.

### C04 — Projeção staged, eventos e invalidação seletiva

**Prioridade:** P1. **Achados:** A03 e parte de A12.

**Arquivos:** `ui_backend/read_models.py`, `events.py`, `routes.py`, `workflow/orchestrator.py`, `web/src/api/events.ts`, `ProductionWorkspace.tsx`; novos testes `tests/test_staged_read_models.py` e `web/src/api/events.test.ts`.

- [ ] Testar produção real persistida pelo coordenador aparecendo como um recurso staged com perfil, snapshot e seis resultados agregados.
- [ ] Unificar cursor de snapshot, histórico paginado e SSE; não usar run_id como produção agregada nem como formato improvisado de cursor.
- [ ] Testar evento entre snapshot/assinatura e durante queda, verificando replay único e ordenado com cursor enviado.
- [ ] Corrigir eventos nomeados e atualizar snapshot/artefatos, não somente a lista de mensagens.
- [ ] Implementar retentativa/backoff sem resetar contagem de falha continuamente; preservar dados com indicação de desconexão.
- [ ] Remover revisão global/metadados irrelevantes da chave de reutilização; fixar contexto de memória aplicável por produção.
- [ ] Consumir o plano de invalidação em operações reais de retrabalho, não somente como preview da UI.
- [ ] Executar testes novos, `tests/test_ui_events.py` e testes de workspace.

**Aceitação:** produção criada/alterada aparece e avança sem refresh manual; trocar música não refaz pesquisa.

### C05 — Pesquisa profunda e roteiro produtivos pelas entradas públicas

**Prioridade:** P1. **Achados:** A05.

**Arquivos:** `workflow/services.py`, `workflow_cli.py`, `stages/research.py`, `stages/script.py`, adaptadores LLM/research existentes, preflight; novo `tests/test_production_service_wiring.py`.

- [ ] Criar `test_default_cli_research_discovers_fetches_and_persists_evidence` sem substituir build_runners; controlar apenas fronteiras externas.
- [ ] Conectar descoberta temática, conteúdo persistido e extrator de produção; fornecer seeds pela CLI/API sem torná-las obrigatórias para toda pesquisa.
- [ ] Remover o modo genérico de tema/URL como fallback produtivo silencioso; falta de material gera pendência explícita.
- [ ] Injetar geração editorial real usando dossiê, idioma, nicho, memória e alvo de duração; manter builder determinístico apenas em modo de teste explicitamente escolhido.
- [ ] Testar claims contraditórias/não sustentadas e qualificação na fala; não basta ID existir.
- [ ] Testar roteiro longo com revisão de coerência/direção e orçamento definido; contagem de palavras é estimativa, não prova do runtime.
- [ ] Executar testes novos e regressões de pesquisa/roteiro/proveniência.

**Aceitação:** fornecer um tema pelas entradas normais gera um dossiê real e um roteiro editorial correspondente, sem injeção manual de runners pelo operador.

### C06 — Aquisição de mídia, identidade segura e voz efetiva

**Prioridade:** P1. **Achados:** A06.

**Arquivos:** `stages/media.py`, `integrations/tts.py`, `stages/narration.py`, `workflow/services.py`, adaptadores stock; novos testes em `tests/test_stage_media.py` e `tests/test_stage_narration.py`.

- [ ] Reproduzir URL como candidate_id no caminho provider → MediaStage, com arquivo local existente.
- [ ] Usar identidade/hash/nome seguro para arquivos, mantendo URL e ID externo como metadados; verificar containment no destino.
- [ ] Resolver provedor/voz/idioma reais a partir do perfil e capabilities verificadas.
- [ ] Testar ausência do modelo e mudança de engine/voz; impedir degradação não permitida para outro idioma/qualidade.
- [ ] Registrar configuração efetiva e falha de capacidade claramente no preflight e no resultado.
- [ ] Manter direitos/atribuição e rejeições isoladas por canal; executar testes pertinentes.

**Aceitação:** o adaptador produtivo roda no Windows e a voz usada corresponde ao contrato do perfil.

### C07 — Projeto FilmCraft correto, todas as faixas e sincronização

**Prioridade:** P1. **Achados:** A07.

**Arquivos:** `workflow/planning.py`, `stages/editing.py`, `integrations/filmcraft.py`; novos testes `tests/test_multishot_audio_sync.py` e `tests/test_editor_project_identity.py`.

- [ ] Criar teste com vários planos por cena, pausas e transições, exigindo limites de cena e fim coerente do áudio/vídeo.
- [ ] Distribuir planos dentro da duração real da cena; modelar pausas e sobreposições sem somá-las indevidamente à fala.
- [ ] Materializar faixas de narração, textos, legendas e música quando previstas no plano; o editor de teste deve verificar cada chamada, não só contar vídeo.
- [ ] Abrir/criar/salvar o projeto da produção antes de inspecionar/reconciliar; usar identidade de produção e mídia em conjunto com shot_id.
- [ ] Comparar fonte, intervalo, destino e digest do item antes de reutilizar; corrigir item alterado em vez de ignorá-lo.
- [ ] Testar dois episódios com IDs de cenas iguais e mídias diferentes; testar retomada após mutação parcialmente aplicada.
- [ ] Adaptar comandos/parâmetros ao catálogo realmente negociado e aguardar job de exportação quando assíncrono.
- [ ] Validar stream de áudio, projeto salvo e ausência de mídia offline; executar todos os testes de montagem/editor.

**Aceitação:** exportação representa o plano inteiro e pertence ao episódio certo, com sincronização e retomada idempotentes.

### C08 — QC substantivo e pacote final recuperável

**Prioridade:** P1. **Achados:** A09.

**Arquivos:** `stages/review.py`, `stages/editing.py`, `publisher.py`, geração de thumbnail/legendas/metadados; novo `tests/test_complete_delivery_package.py`.

- [ ] Testar pedido de 25 minutos com arquivo de 10 segundos, claim sem evidência, mídia offline e composição ainda não produzida; todos devem falhar explicitamente.
- [ ] Validar runtime medido contra a faixa/alvo configurados e stream de áudio do master, não apenas bundle de narração.
- [ ] Exigir composição materializada para resolver lacuna; texto de estratégia sozinho não comprova imagem.
- [ ] Gerar e incluir thumbnail, títulos, capítulos, SRT/VTT, descrição, fontes, direitos, projeto FilmCraft, mídias dependentes e relatório.
- [ ] Persistir prévia e projeto como artefatos com integridade, em vez de apenas strings de caminho.
- [ ] Mover pacote para diretório temporário diferente e validar referências sem depender do workspace original.
- [ ] Executar teste de pacote e regressões de revisão/publicação, preservando approval pending.

**Aceitação:** pacote aprovado satisfaz a lista de entregas original e pode ser inspecionado/restaurado em outro diretório.

### C09 — Base de perfil, patches, reversão e escopo de memória

**Prioridade:** P1. **Achados:** A11 e parte de A12.

**Arquivos:** `profiles/store.py`, `profiles/context.py`, modelos/migrações e testes de memória existentes; novo `tests/test_learning_state_reconstruction.py`.

- [ ] Reproduzir sequência música antiga → regra de outro campo → música nova, com IDs em ordens diferentes.
- [ ] Separar configurações explícitas/base dos efeitos inferidos. Aplicar apenas operações do patch em ordem de linhagem definida, nunca snapshots inteiros por aprendizagem.
- [ ] Testar suspensão após alterações explícitas e regras independentes; reconstruir valores preservando escolhas posteriores do usuário.
- [ ] Avaliar condição e compatibilidade antes de materializar efeitos; uma regra excluída deve ter efeito excluído, não apenas ID oculto.
- [ ] Rejeitar reutilização de candidate_id/avaliação de outro perfil; escopo obrigatório nas leituras/mutações de memória.
- [ ] Definir migração reversível dos dados atuais e backup antes de alterar armazenamento; não apagar histórico para simplificar correção.
- [ ] Executar testes de store/contexto/isolation e reconstrução.

**Aceitação:** perfil efetivo é determinístico, regras substituídas não ressurgem e reversão preserva preferências explícitas atuais.

### C10 — Aprendizado operacional com evidência e orçamento reais

**Prioridade:** P1. **Achados:** A10 e parte de A12.

**Arquivos:** `profiles/learning.py`, `profiles/store.py`, `workflow/services.py`, `workflow/orchestrator.py`, feedback CLI/API; novo `tests/test_operational_autonomous_learning.py`.

- [ ] Criar `test_observation_without_artifact_cannot_activate_learning` e teste de avaliação sem checks/ensaio.
- [ ] Vincular avaliação ao digest/versão imutável do candidato e verificar evidência, hash/resultado e política no ponto transacional de ativação.
- [ ] Ligar revisor e avaliadores à composição padrão, aos hooks de conclusão/falha/feedback e às mudanças de ferramenta.
- [ ] Preservar autonomia: propostas verificadas são ativadas sem confirmação humana; insuficiência mantém hipótese com motivo.
- [ ] Fixar corte/IDs de contexto da produção, limitar seleção de histórico e impedir que nova observação altere seu digest retroativamente.
- [ ] Registrar tentativas reais, idempotência de propostas/avaliações e consumo persistido de chamadas/tempo/tentativas/ensaios.
- [ ] Criar jornada produção A → observação → ensaio → regra ativa → efeito observado no serviço da produção B, sem substituir coordenador ou learner por um resultado constante.
- [ ] Testar suspensão automática quando falha relacionada ou versão incompatível é observada.
- [ ] Executar regressões de aprendizagem/coordenador; não calibrar pesos estéticos para encobrir ausência de avaliação.

**Aceitação:** memória aprende e afeta a próxima produção por um caminho operacional real, com efeito verificável e reversível.

### C11 — Perfis e memória corretos na interface

**Prioridade:** P1/P2. **Achados:** A13.

**Arquivos:** `ui_cli.py`, `ui_backend/app.py`, `profile_adapter.py`, DTOs, `profiles/store.py`, `ProfileForm.tsx`, `ProfileList.tsx`, `MemoryList.tsx`, `LearningDetails.tsx`; novos testes reais de integração API/perfil.

- [ ] Permitir criar primeiro perfil em instalação limpa; capabilities e adaptador precisam concordar.
- [ ] Testar navegação A → B → A → B com ambos em cache, garantindo campos/ID corretos e sem vazamento.
- [ ] Persistir campos que a UI deixa editar, incluindo nome/idioma/nicho/settings; ou apresentar claramente como read-only os campos sem operação suportada.
- [ ] Projetar nome/idioma reais e revisão atual; atualizar queries após save e permitir dois saves consecutivos.
- [ ] Traduzir NotFound/ScopeViolation/RevisionConflict para HTTP 404/409 adequados, usando o adapter real nos testes.
- [ ] Remover revisão fixa 1 de memória/suspensão; coletar feedback verdadeiro com etapa/evidência, sem texto constante.
- [ ] Incluir candidatos/avaliações/condições/before-after e atualização automática da memória; não exigir aprovação humana para ativação.
- [ ] Preservar as correções de nicho já entregues e regenerar tipos a partir do OpenAPI.
- [ ] Executar testes API/UI e jornada de criação/edição/suspensão com ProfileStore real.

**Aceitação:** perfis e memória exibidos correspondem aos dados persistidos e não se misturam entre canais/abas.

### C12 — Inspetores e handlers ligados às entregas

**Prioridade:** P2. **Achados:** A14, A02 e A03.

**Arquivos:** `ProductionWorkspace.tsx`, inspetores em `web/src/features/stages/`, cliente API, DTOs e consultas backend; teste de workspace com bundles reais de teste.

- [ ] Adicionar consulta/resolução de bundles por produção/etapa e fornecer os dados aos inspetores a partir do componente pai.
- [ ] Testar evidência da pesquisa, fala/direção, áudio por segmento, licença da mídia, projeto/prévia e resultado da revisão na mesma jornada.
- [ ] Ligar Retomar, retry, abrir editor, reconciliar, corrigir roteiro e substituir mídia às operações de C03.
- [ ] Mostrar pendência somente quando a entrega estiver realmente ausente; não renderizar placeholder permanente apesar de arquivos válidos.
- [ ] Validar o resultado da ação por estado/artefato, não apenas por toast ou receipt 200.
- [ ] Executar os testes de workspace/inspetores e typecheck/build.

**Aceitação:** entregas e operações ficam acessíveis na tela que o usuário utiliza, sem depender de props fornecidas somente por testes isolados.

### C13 — Regressão cruzada, piloto e documentação baseada em evidência

**Prioridade:** fechamento obrigatório. **Achados:** todos; cobertura insuficiente dos critérios originais.

**Arquivos:** `web/e2e/`, `scripts/e2e_serve.py`, testes de integração novos, `docs/interface-grafica.md`, `docs/profile-memory.md`, `docs/filmcraft-setup.md`, README e checklists dos planos.

- [ ] Criar E2E que de fato clique iniciar e atravesse API/worker/coordenador/runners reais com transportes externos determinísticos; não substituir submit/execute por retorno pronto.
- [ ] Testar falha de revisão, geração de pacote, alteração de roteiro e retomada seletiva.
- [ ] Testar eventos durante queda SSE, refresh, fechamento da aba e restart da API com worker ainda ativo.
- [ ] Testar dois perfis, aprendizagens diferentes, troca de perfil em cache e job idempotente.
- [ ] Executar matriz de testes direcionados, suíte completa, tipos, build e E2E, separando falhas preexistentes e recursos sem ambiente.
- [ ] Com ferramentas/provedores explicitamente configurados, executar amostra curta real e verificar áudio, texto, projeto/preview e exportação do FilmCraft.
- [ ] Executar piloto longo de 20–30 minutos; registrar duração medida, recursos, custo conhecido/desconhecido, correções e evidência do pacote editável.
- [ ] Demonstrar aplicação de aprendizado na produção seguinte e reversão após falha relacionada.
- [ ] Atualizar documentação e checkboxes pelo resultado observado. Checkbox marcado não deve significar “arquivo criado” quando a exigência era jornada operacional.

**Aceitação:** somente após essa evidência declarar os marcos operacionais completos. Continuar identificando testes determinísticos e piloto real separadamente.

## 9. Ordem de execução e marcos

| Marco | Tarefas | Critério para avançar |
|---|---|---|
| R0 — Estado honesto e configuração efetiva | C01, C02 | Sem sucesso falso; valores do perfil chegam aos runners |
| R1 — Entradas operacionais | C03, C04 | UI/CLI usam serviços reais, produção consultável e eventos convergentes |
| R2 — Conteúdo/montagem/pacote | C05–C08 | Tema → materiais → projeto/áudio/vídeo → pacote íntegro |
| R3 — Memória segura e ativa | C09, C10 | Regras aplicadas corretamente, avaliação real e próxima produção afetada |
| R4 — Jornadas completas de interface | C11, C12 | Perfis/inspetores/ações reais disponíveis sem terminal |
| R5 — Aceitação de ponta a ponta | C13 | Regressões e piloto registrados, limitações explícitas |

Dependências principais: C01/C02 antes de fechamento funcional; C03 habilita ações e execução via UI; C04 acompanha C03; C05/C06 alimentam C07/C08; C09 precisa preceder ativação automática de C10; C11 depende de correção dos contratos de perfis/memória; C12 consome C03/C04/C08; C13 fecha o conjunto.

## 10. Critérios para considerar os planos atendidos

- [ ] Um tema fornecido pelas entradas normais inicia pesquisa real sem injeção manual de runners.
- [ ] UI não oferece conclusão/recurso que o backend ainda não consegue executar.
- [ ] Uma submissão tem produção/job consultáveis imediatamente, sem 404 artificial pós-receipt.
- [ ] As seis etapas operam com o perfil correto, parâmetros efetivos e evidências.
- [ ] Voz, planos, pausas e todas as faixas aparecem na exportação do episódio correto.
- [ ] Reprovação de revisão bloqueia a entrega e é visível na CLI/API/GUI.
- [ ] Aprovação produz pacote íntegro, completo e recuperável como projeto editável.
- [ ] Retomada, stop, retrabalho e reconciliação têm efeitos observáveis e idempotentes.
- [ ] SSE e consulta de produção convergem após refresh/restart/desconexão.
- [ ] Configurações explícitas e aprendizadas têm efeito real e isolamento por canal.
- [ ] Aprendizado passa por evidência/ensaio adequados e pode ser aplicado automaticamente.
- [ ] Suspensão não apaga preferências recentes nem deixa efeito de regra incompatível.
- [ ] Contexto de produção é estável; alterações independentes não invalidam etapas sem necessidade.
- [ ] Testes cruzam as fronteiras antes omitidas, com doubles somente em serviços externos.
- [ ] Piloto real comprova duração, áudio, material visual, projeto e pacote final.
- [ ] Relatórios distinguem claramente implementação, teste determinístico e capacidade validada em ambiente real.

## 11. Limite desta auditoria

Esta auditoria comprova a necessidade de continuidade, mas não promete ausência de todos os defeitos possíveis. As reproduções focaram contratos quebrados e jornadas centrais. Não foi realizada uma revisão pixel a pixel de todas as telas, uma avaliação jurídica de licenças nem um benchmark de qualidade dos modelos.

As correções propostas não exigem refazer o design system ou abandonar a arquitetura. A maior parte do investimento deve ser em conexão entre serviços, preservação de estado e testes que executem as mesmas entradas usadas pelo operador.

---

## 12. Resultado da execução (26/11/2026)

As tarefas C01–C12 foram executadas em worktree isolado (`auditoria-correcao`) com seus
commits focados. Os checkboxes acima permanecem como registro do plano original; o estado
verificado está abaixo e em `docs/correcao-2026-11-26.md`.

- **C01–C12**: concluídas com teste de regressão executado antes da correção (evidência RED
  em worktree temporário) e suíte verde depois. Os contratos de estado honesto, serviços
  compartilhados, projeção staged, conteúdo, montagem, pacote, memória e interface estão
  materializados e exercitados por testes que atravessam as fronteiras antes omitidas.
- **C13 — parte determinística**: concluída. Matriz final: 1230 Python aprovados (6 ignorados,
  com os três arquivos longos excluídos), 49 testes frontend, typecheck, build e 5 E2E
  aprovados, incluindo jornada que clica "Iniciar produção" e atravessa API → worker →
  coordenador → serviços com transportes determinísticos. Documentação de evidência escrita.
- **C13 — piloto real**: **pendente**. Não houve download de modelo, gasto de crédito nem
  produção de vídeo longo, conforme Global Constraint deste plano. Duração medida, custo,
  qualidade de voz e compatibilidade com FilmCraft real permanecem sem comprovação.
- **Cobertura parcial registrada**: cenários de timeout de ação externa com editor real e
  dupla aba simultânea foram exercitados por testes de serviço/jobs e por dois cliques rápidos
  no navegador com a mesma chave de idempotência, não por dois contextos de navegador
  simultâneos; são considerados verificados no domínio, não em E2E de duas abas.


