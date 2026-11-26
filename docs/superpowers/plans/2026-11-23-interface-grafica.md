# AI Video Factory — Interface gráfica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Delegate only when the execution method authorizes it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma interface gráfica local para operar canais/perfis, iniciar e acompanhar produções, inspecionar os seis estágios, revisar entregas e consultar a memória autônoma de cada canal.

**Architecture:** Aplicativo web local em TypeScript/React, servido por uma API Python/FastAPI, com eventos SSE e workers de produção independentes das abas do navegador. A API adapta os serviços Python e o RunStore existentes; o navegador não reimplementa o pipeline, não acessa SQLite diretamente e não controla o MCP do FilmCraft diretamente.

**Tech Stack:** TypeScript, React, Vite, React Router, TanStack Query, CSS Modules e tokens CSS; Python 3.12, FastAPI, Uvicorn, SQLite e Pydantic; Vitest, React Testing Library, MSW, Playwright e pytest para verificação.

**Spec:** Este documento é autocontido. As seções 1–10 definem produto, arquitetura e contratos; as seções 11–15 detalham tarefas, dependências e aceitação. Complementa o [plano dos seis estágios, memória e FilmCraft](2026-11-23-canal-dark-estagios-memoria-filmcraft.md).

**Data:** 23 de novembro de 2026.

**Estado:** Plano de implementação. A interface, API e comandos novos ainda não existem. A escrita deste arquivo não implementa o produto.

## Global Constraints

- Linguagem escolhida para a interface: **TypeScript**. React renderiza as telas; o processamento permanece em Python.
- Entrega inicial: aplicativo local aberto no navegador, no Windows. Empacotamento como janela desktop é posterior.
- O assunto acompanhado é a produção de vídeos e suas operações. Um gerenciador de tarefas de desenvolvimento de software está fora deste escopo.
- Preservar Python `>=3.12,<3.13` e os contratos existentes durante a migração.
- Interface em português brasileiro; idioma dos vídeos é uma configuração independente de cada perfil.
- A interface chama serviços estruturados, sem executar textos de comandos fornecidos pelo navegador nem analisar a saída humana do CLI como contrato.
- O mesmo perfil e a mesma produção precisam mostrar o mesmo estado na interface e no CLI.
- Usar capacidades do backend para habilitar ações. Não apresentar como disponível uma etapa que ainda não foi implementada/configurada.
- Memória continua autônoma: não introduzir uma aprovação obrigatória para cada aprendizado.
- Publicação continua separada: esta interface não ganha upload/publicação automáticos por consequência da autonomia da memória.
- Fechar ou atualizar a aba não interrompe uma produção. Reiniciar a API não deve lançar uma segunda execução da mesma solicitação.
- Mostrar progresso, duração, custo e uso de recursos somente quando medidos ou explicitamente identificados como estimativa. Nunca simular percentuais ou ETA.
- Credenciais, tokens do editor e respostas integrais potencialmente sensíveis não entram no frontend nem em seus logs.
- Não modificar ou descartar alterações em andamento no repositório. Este plano parte do estado observado; execução começa por inventário e revisão dos arquivos atuais.
- Ajustes finos de edição, voz e avaliação da memória continuam adiados, conforme decisão anterior do usuário.

## Review Focus

1. Reconexão de eventos após queda: o estado converge sem perder falhas nem duplicar entradas. Cobertura: tarefas UI-3 e UI-7.
2. Duplo clique, retry HTTP ou duas abas: iniciar a mesma solicitação não cria dois workers. Cobertura: tarefas UI-4 e UI-6.
3. Troca de canal durante uma requisição: dados e ações do canal anterior não aparecem no novo perfil. Cobertura: tarefas UI-2, UI-6 e UI-10.
4. Vídeo longo, arquivo grande e busca no player: servir mídia com Range, sem carregar o vídeo inteiro em memória. Cobertura: tarefas UI-8 e UI-12.
5. Pedido de parada durante comando externo do editor: mostrar solicitação pendente e confirmar o estado observado, sem declarar cancelamento inexistente. Cobertura: tarefas UI-4 e UI-9.

---

## 1. Resposta ao diagnóstico e relação com o plano principal

O plano anterior mencionava explicitamente a interface visual de perfis e memória como trabalho adiado. Sua primeira entrega usava CLI, arquivos e relatórios. Portanto, a interface estava reconhecida, mas não tinha telas, API ou tarefas próprias de implementação.

Este plano promove a interface a uma frente concreta. Pode começar antes de todos os estágios novos estarem prontos: a primeira entrega acompanha execuções e artefatos que já existem; os controles de perfil e do fluxo novo entram conforme os serviços correspondentes ficam disponíveis.

### Estado observado no repositório

- `run_store.py` já mantém manifests, entradas, estados, eventos JSONL, heartbeat e integridade dos artefatos.
- `cli.py`, `video_pipeline.py`, `daily_job.py` e `scheduler.py` são interfaces de operação existentes, com caminhos distintos.
- `remotion/` contém React/TypeScript para composição de vídeo, não um painel de operação da fábrica.
- O plano de perfis/coordenador/FilmCraft ainda é especificação; não assumir que os módulos novos já foram criados.
- Existem alterações de suporte Windows no workspace, incluindo `file_lock.py`, `platform_support.py` e documentação. Reaproveitar a versão vigente, em vez de executar novamente uma correção já entregue.

Não avaliar a compatibilidade de todos os comandos apenas porque uma amostra sintética passou. A GUI deve distinguir ferramenta instalada, integração configurada e capacidade efetivamente validada.

## 2. Escolha da linguagem e do formato

| Opção considerada | Benefício | Custo/limite | Decisão |
|---|---|---|---|
| **TypeScript + React, web local** | Boa composição de telas, player de mídia, atualização incremental e contratos tipados; aproveita familiaridade técnica já presente em Remotion | Exige uma API Python local e build do frontend | **Escolhida** |
| Python + PySide6 | Uma linguagem para UI e processamento, com widgets desktop | Exige outra abordagem de UI e distribuição; visualização rica de entregas e mídia demanda mais integração | Alternativa válida, sem preferência neste projeto |
| TypeScript + Tauri | Janela desktop e integração nativa | Acrescenta Rust, empacotamento e ciclo de releases à primeira entrega | Considerar depois de validar o produto local |

A escolha é delegada pelo usuário. O backend permanece Python para reutilizar a aplicação; TypeScript é a linguagem da interface, não uma reescrita do AI Video Factory.

Vite gera arquivos estáticos para distribuição. Depois do build, Node não precisa executar em paralelo para usar a interface empacotada com Python. React Router organiza navegação; TanStack Query mantém dados remotos com chaves que incluem perfil e produção. CSS Modules e tokens CSS evitam acrescentar um framework visual inteiro na primeira versão.

Documentação primária de referência: [React com TypeScript](https://react.dev/learn/typescript), [Vite](https://vite.dev/guide/), [arquivos estáticos no FastAPI](https://fastapi.tiangolo.com/tutorial/static-files/) e [SSE no navegador](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events). Conferir versões compatíveis e fixá-las nos lockfiles ao implementar; não copiar versões do pacote de renderização sem verificar as necessidades do painel.

## 3. Trabalho que a interface deve facilitar

O operador precisa responder rapidamente:

1. Qual canal e qual episódio estou acompanhando?
2. O que já terminou, o que está acontecendo e o que vem depois?
3. Há um problema? Onde ele ocorreu e qual ação o resolve?
4. Posso ver as fontes, o roteiro, ouvir a voz e assistir à prévia?
5. Que configurações e aprendizados o agente usou ou alterou?

A tela principal é uma área de trabalho da produção, não um chatbot. O primeiro objetivo visual é tornar os seis estágios compreensíveis; logs técnicos ficam em uma área expansível.

### Jornadas essenciais

- Abrir a aplicação e encontrar uma produção em andamento.
- Selecionar/criar perfil, informar tema e iniciar uma produção válida.
- Acompanhar pesquisa, abrir uma evidência e ler o roteiro gerado.
- Ouvir a narração e inspecionar as mídias escolhidas.
- Ver prévia/final, conferir pendências e abrir o projeto no FilmCraft quando disponível.
- Corrigir um insumo ou registrar feedback e retomar somente as etapas necessárias.
- Consultar um aprendizado aplicado automaticamente, com evidência e versão anterior.
- Sair do navegador, voltar e encontrar o estado real preservado.

## 4. Escopo de telas

### 4.1 Produções

Tela inicial com lista/tabela das produções e filtro por perfil, estado e período. Colunas: título/tema, canal, etapa atual, estado, início e última atualização. Na primeira versão, busca por texto e ordenação simples; sem gráficos decorativos ou números de audiência inexistentes.

Uma produção que exige atenção aparece com causa resumida e ação aplicável: “Voz indisponível para o idioma do perfil”, por exemplo. Identificadores técnicos ficam nos detalhes/cópia, não como título principal.

Estados vazios distinguem “nenhuma produção”, “nenhuma produção neste filtro” e “não foi possível carregar”. A primeira condição oferece “Nova produção”; a segunda, limpar filtro; a terceira, tentar novamente.

### 4.2 Nova produção

Campos: perfil, tema, recorte opcional, duração alvo e fontes iniciais opcionais. Idioma/voz/formato são herdados do perfil e mostrados em resumo, sem obrigar a repetir a configuração.

Antes de iniciar, consultar preflight/capacidades e apresentar pendências acionáveis. O usuário pode executar somente até pesquisa/roteiro se o restante não estiver configurado. O botão mantém o texto “Iniciar produção”; depois do clique, navega para a produção criada.

Cada submissão gera uma chave de idempotência preservada durante retries. “Salvar rascunho” salva a solicitação sem iniciar execução; não confundir o rascunho de formulário com uma produção já em andamento.

### 4.3 Área da produção

Cabeçalho com tema, perfil, versão usada, estado e ação principal pertinente. Lista ordenada dos seis estágios à esquerda ou no topo; área principal mostra o estágio selecionado.

Cada etapa informa estado, atividade humana compreensível, tempo decorrido, última evidência de atividade e entregas disponíveis. Se houver progresso medido, mostrar a unidade: “12 de 20 segmentos de voz”, “380 de 900 quadros”. Sem total conhecido, mostrar atividade sem percentual.

“2 de 6 etapas concluídas” representa contagem de etapas, não 33% do tempo estimado. Não ponderar as etapas igualmente para fabricar uma barra de duração. Estimativa de término só aparece quando o backend a fornece com origem e validade.

Abas da produção: **Etapas**, **Arquivos**, **Histórico** e **Memória utilizada**. A seleção de uma etapa permanece estável enquanto eventos chegam; atualizações não roubam foco ou fazem a página saltar.

### 4.4 Inspetor de cada estágio

| Etapa | Conteúdo central | Ações previstas quando disponíveis |
|---|---|---|
| Pesquisa | Subquestões, fontes, afirmações/evidências, contradições e síntese | Abrir fonte; ler trecho; baixar dossiê; solicitar aprofundamento |
| Roteiro | Capítulos, cenas, fala e direção em colunas distintas; referências de fontes | Editar rascunho; comparar versão; salvar correção e solicitar retrabalho |
| Narração | Player por cena/segmento, texto falado, duração e voz efetiva | Ouvir; registrar problema; regenerar segmentos selecionados |
| Mídia | Lista de planos com miniaturas, fonte, licença e associação à cena | Ver original; trocar por candidato já adquirido; importar arquivo próprio |
| Edição | Estado do FilmCraft, montagem resumida, prévia, exportação e avisos | Abrir projeto no editor; exportar; reconciliar estado após edição manual |
| Revisão | Player final, verificações, pendências, metadados e pacote | Encaminhar correção; baixar arquivos; registrar feedback |

Cada ação depende de uma operação implementada no domínio. Exibir dependência ausente de forma clara; não construir um botão que apenas simula sucesso. Editar fala exige versionamento e invalidação reais, não alteração isolada de um arquivo no frontend.

### 4.5 Perfis

Listar, criar e editar perfis. Formulário por grupos: identidade, pesquisa, roteiro, voz, mídia, edição e revisão. Mostrar valores herdados versus explícitos e o que será usado nas próximas produções.

Salvar usa revisão esperada. Se outra aba ou o agente já alterou o perfil, apresentar o conflito e comparação; não sobrescrever silenciosamente. Produções em andamento mantêm seu snapshot e a tela explica isso junto à ação de salvar.

O exemplo de catolicismo continua apenas exemplo do plano anterior. A interface não cria um canal religioso automaticamente.

### 4.6 Memória do canal

Lista de aprendizados e observações filtrada por etapa e estado: hipótese, em avaliação, ativo, suspenso ou substituído. Detalhe mostra condição de aplicação, antes/depois, evidências, avaliação, versão e produções afetadas.

Uma atividade visível informa mudanças automáticas do agente. Não criar uma fila obrigatória de aprovação: o usuário já escolheu aplicação autônoma. Intervenções manuais opcionais incluem registrar feedback, suspender aprendizado e restaurar uma configuração quando o serviço correspondente existir.

Comparação deve distinguir configuração explícita, inferência do agente e dado observado. “Funcionou sem erro” não deve aparecer como prova de qualidade estética ou de aumento de audiência.

### 4.7 Ferramentas e diagnóstico

Mostrar estado de LLM, voz, provedores de mídia, FFmpeg, navegador e FilmCraft. Estados separados: não instalado, instalado, não configurado, indisponível, validado e não verificado, conforme evidência disponível.

Testes de conexão ou geração que façam trabalho externo são ações explícitas, não efeitos automáticos de abrir a página. Valores secretos ficam fora dos DTOs. Mostrar apenas “configurada/não configurada” para credenciais; configuração avançada por ambiente/arquivo permanece documentada na primeira versão.

### 4.8 Histórico e relatórios

Eventos paginados, com resumo legível e detalhes técnicos expansíveis. Filtro por etapa, severidade e tentativa; opção de acompanhar os novos eventos sem forçar rolagem quando o usuário está lendo um evento antigo.

Exibir custo somente se medido, com moeda e origem. Sem essa informação, mostrar “Não informado”. Consumo de recursos só aparece quando coletado; não criar estimativas numéricas a partir do nome do modelo.

## 5. Direção visual e comportamento

### Direção escolhida

Área de produção com lista sequencial de estágios e inspetor de entregas. É o elemento distintivo: o usuário acompanha uma linha de produção documental, podendo abrir qualquer resultado já produzido.

Alternativas consideradas: um kanban privilegia fila de episódios, mas mostra mal a evidência de cada etapa; um canvas de nós favorece configurar fluxos, porém acrescenta navegação e complexidade antes de existir necessidade de editar o grafo. A lista de produções e o inspetor cobrem a primeira versão.

### Fundação proposta

- Tema claro inicial, fundo neutro, superfície branca e um destaque azul para ação/foco. Modo escuro fica para uma iteração posterior.
- Tokens iniciais: fundo `#F5F6F8`, superfície `#FFFFFF`, texto `#182230`, texto secundário `#475467`, destaque `#175CD3`. Ajustar estados respeitando contraste medido.
- Fonte de interface: pilha de sistema, usando Segoe UI no Windows; monoespaçada apenas em detalhes técnicos.
- Três tamanhos por tela: título 24px, corpo 16px e apoio 14px; pesos 400/500, sem títulos excessivamente pesados.
- Escala de espaço: 4, 8, 12, 16, 24, 32 e 48px. Agrupar por proximidade antes de acrescentar caixas.
- Preferir tabelas/listas e divisões claras a uma grade de cartões. Cor de estado sempre acompanhada de texto.
- Layout pensado primeiro para desktop; adaptar a 768px e a 390px sem rolagem horizontal da página. Em telas estreitas, o inspetor abre abaixo da lista de etapas.
- Controles acessíveis por teclado, foco visível, rótulos explícitos, alvos de toque adequados e respeito a movimento reduzido.
- Fontes e ícones locais; não depender de CDN para abrir a aplicação.

### Estados obrigatórios

Cada tela deve cobrir: carregamento inicial, vazio, erro recuperável, conteúdo parcial, conexão interrompida e estado atualizado. Preservar o último snapshot ao perder conexão, mostrando “Sem conexão — dados da última atualização”, sem apresentar os dados como atuais.

Erros explicam o que falhou e a ação possível. Stack trace, IDs e saída bruta ficam em detalhes copiáveis, com segredos redigidos. Notificações transitórias não podem ser o único lugar onde uma falha de produção aparece.

## 6. Arquitetura técnica

```text
navegador local / React
        | HTTP JSON + SSE autenticados, mesma origem
        v
FastAPI: consultas + comandos + artefatos + arquivos estáticos
        |
        +-- adapters de consulta --> RunStore / perfis / bundles existentes
        |
        +-- journal de jobs --> worker Python de produção
                                      |
                                      +--> coordenador dos seis estágios
                                      +--> provedores / TTS / FilmCraft MCP
                                      +--> resultados, eventos e snapshots
```

### 6.1 Separação de responsabilidades

- **Frontend:** formulários, navegação, players e apresentação de estado remoto. Estado local do navegador guarda somente rascunhos/preferências de tela sem segredos.
- **API:** valida contratos, resolve escopo, consulta serviços e aceita operações. Não executa um documentário inteiro dentro de uma requisição HTTP.
- **Worker:** processo independente que chama serviços estruturados e persiste progresso. Sessões de editor/modelo pertencem a ele, não à conexão SSE.
- **Domínio existente/planejado:** continua dono de perfis, memória, retomada e integridade.
- **Journal de controle:** guarda solicitações/estado de jobs e eventos de apresentação; não vira outra fonte de verdade para conteúdo e configurações de canal.

### 6.2 Persistência adicional

Arquivo proposto: `data/ui/control.sqlite3`, com migrações, jobs, chaves de idempotência e cursor de eventos/projeções. Separado de `data/profiles/profiles.sqlite3` para não acrescentar tabelas da UI ao domínio de perfis.

O worker grava resultado/manifest no domínio e publica um evento de controle idempotente referenciando a evidência. Se cair entre as gravações, uma reconciliação compara a evidência persistida e corrige o journal. O estado técnico da produção é derivado dos manifests, não de uma mensagem otimista do frontend.

Para o legado, implementar índice de consulta somente leitura com cursor por arquivo/offset. Arquivos de eventos são append-only, mas uma última linha parcial pode existir após queda: ignorar a linha incompleta até ser concluída ou registrar falha de integridade. Não alterar o arquivo para “consertar” a leitura.

### 6.3 Execução de longa duração

Persistir pedido e idempotência antes de lançar processo. Um único despachante local reivindica jobs por transação/lease; workers se identificam por ID de job, com heartbeat e evidência de processo. PID sozinho não comprova que o processo ainda é o mesmo.

Usar processo Python com argumentos fixos, sem shell e sem segredos na linha de comando. No Windows, iniciar sem abrir janelas de console extras. Após reiniciar a API, consultar jobs e reconciliar workers em vez de relançar tudo.

Inicialmente, uma produção pesada ativa por vez; outras aguardam na fila. O valor é uma política operacional proposta para proteger os recursos locais, independente dos ajustes finos de edição. O usuário vê a posição na fila e pode cancelar um job ainda não iniciado.

Não usar apenas `BackgroundTasks` do servidor para trabalhos que precisam sobreviver ao ciclo de vida de uma aba ou a um restart da API.

### 6.4 Progresso e eventos

Consultas retornam snapshot + cursor. SSE continua a partir desse cursor, inclusive após reconexão com `Last-Event-ID`. Eventos têm ID monotônico persistido, escopo, tipo, horário e payload tipado.

Tipos iniciais: `production.updated`, `stage.started`, `stage.progress`, `stage.completed`, `stage.failed`, `artifact.available`, `memory.updated`, `job.updated` e `connection.reset_required`.

Dados de progresso incluem unidade, concluído, total opcional e origem. Sem total válido, o frontend mostra atividade indeterminada. Atualizações de quadro/amostra são agregadas antes de chegar à UI, evitando um evento por quadro.

Um cursor expirado ou perdido gera pedido de novo snapshot; não fingir replay completo. SSE é somente leitura; ações usam HTTP. Se SSE falhar, fallback para consulta periódica com backoff e pausa quando a tela estiver oculta, respeitando o estado da produção.

### 6.5 Parada, retomada e edição

Na primeira versão, “Parar após a etapa atual” solicita uma parada cooperativa. O estado fica “Parada solicitada” até a etapa atingir um ponto seguro e persistir o resultado. Uma exportação externa que não aceita cancelamento não é declarada cancelada por fechar sua conexão.

Estados de job de controle: `queued`, `running`, `stop_requested`, `stopped`, `completed`, `failed` e `unknown`. Eles não substituem os estados de estágio do RunStore. Retomar usa a mesma produção e a lógica de fingerprints; uma nova tentativa não cria um episódio novo.

Adicionar ao coordenador planejado `control: RunControl | None = None`; o hook consulta parada em pontos seguros e reporta atividade. Não matar processos do editor indiscriminadamente.

Editar roteiro ou substituir mídia cria uma revisão e solicita invalidação seletiva no domínio. Antes de salvar, mostrar o impacto: “Esta mudança refaz narração, mídia dependente, edição e revisão”. Depois de confirmado o salvamento solicitado, a UI acompanha o retrabalho; não introduzir aprovação humana para mudanças autônomas de memória.

### 6.6 Mídia e arquivos

Servir artefatos por ID resolvido no backend e pertencimento à produção/perfil. Não criar endpoint que aceita caminho arbitrário do Windows. Validar raiz resolvida, links/junctions e manifesto antes de abrir um arquivo.

Vídeo/áudio usam resposta com suporte a Range e seek. O frontend usa players nativos e carrega miniaturas/metadata antes de mídia completa. Downloads de pacote têm headers e nomes adequados; vídeos grandes não são lidos inteiros em RAM nem gravados como base64 no estado React.

Markdown de roteiros/dossiês é renderizado sem HTML arbitrário. Fontes externas abrem em outra aba com indicação de origem; texto recuperado não vira HTML executável.

Upload de arquivo próprio é uma operação separada: tamanho/tipo permitidos, nome normalizado, escrita em diretório da produção, hash e confirmação no manifesto. Falha ou interrupção remove somente o upload parcial correspondente.

### 6.7 Sessão local e fronteira de confiança

- Bind somente em loopback, com validação de Host e Origin. Modo rede/multiusuário está fora do escopo.
- Launcher gera um segredo de bootstrap de uso único, transportado no fragmento da URL e trocado por cookie HttpOnly/SameSite estrito. Remover fragmento após troca; não registrar o segredo em logs.
- Mutações exigem sessão e proteção CSRF. SSE/player usam a sessão da mesma origem, sem segredos na query string.
- Em desenvolvimento, usar proxy do Vite para a API e a mesma política de sessão; evitar CORS irrestrito.
- O token do FilmCraft e as chaves dos provedores ficam no processo Python/ambiente, com redação nos eventos.
- Ações locais como abrir projeto/arquivo usam IDs e operações permitidas pelo backend; não aceitar comandos de shell do browser.

Isso define o isolamento de um aplicativo local que controla arquivos e programas. Não inclui contas, nuvem ou fluxo extra de aprovação de tarefas.

## 7. Contratos de API propostos

Prefixo `/api/v1`. DTOs Python/Pydantic são a fonte dos tipos públicos; gerar os tipos TypeScript a partir do OpenAPI. Identificadores opacos são usados em rotas, mas nomes humanos aparecem na interface.

| Método e rota | Entrada/saída e comportamento |
|---|---|
| `GET /capabilities` | Capacidades reais: leitura legada, perfis, fluxo novo, editor, controle de parada e versão da API |
| `POST /session/bootstrap` | Troca segredo de uso único por sessão local; não inicia produção |
| `GET /profiles` | Perfis paginados e estado de disponibilidade |
| `POST /profiles` | Cria perfil usando `ProfileSpec` do plano principal |
| `GET /profiles/{profile_id}` | Snapshot atual e revisão |
| `PATCH /profiles/{profile_id}` | Patch tipado e revisão esperada; conflito retorna 409 |
| `GET /profiles/{profile_id}/memory` | Observações/aprendizados paginados, com filtros de estágio/estado |
| `POST /profiles/{profile_id}/feedback` | Feedback explícito com produção/estágio e referências |
| `POST /profiles/{profile_id}/memory/{learning_id}/suspend` | Suspensão manual opcional com revisão esperada e motivo |
| `GET /productions` | Lista filtrada por perfil/estado, com cursor de paginação |
| `POST /productions/preflight` | Avalia pedido e retorna ações possíveis/pendências; não inicia serviços caros |
| `POST /productions` | Cria produção/job com `Idempotency-Key`; retorna 202 e referências |
| `GET /productions/{production_id}` | Snapshot completo da área de produção, versão e cursor de eventos |
| `GET /productions/{production_id}/stages/{stage}` | Estado, atividades, configuração efetiva e entregas de um estágio |
| `POST /productions/{production_id}/actions` | Ação tipada: `resume`, `stop_after_stage`, `revise_script`, `replace_media`, `reconcile_editor` ou `open_editor`; disponibilidade vem do serviço |
| `GET /productions/{production_id}/events` | Histórico paginado de eventos redigidos |
| `GET /productions/{production_id}/stream` | SSE a partir de cursor/Last-Event-ID |
| `GET /productions/{production_id}/artifacts` | Manifesto de arquivos com IDs, tipos, tamanho e integridade |
| `GET /artifacts/{artifact_id}/content` | Visualização/download autenticado com Range quando apropriado |
| `POST /productions/{production_id}/uploads` | Arquivo próprio para aquisição/substituição posterior, sem executar o conteúdo |
| `GET /jobs/{job_id}` | Estado da solicitação, heartbeat e resultado disponível |
| `GET /tools` | Estado de ferramentas/configuração com segredos omitidos |
| `POST /tools/{tool_id}/check` | Teste explícito permitido pela capacidade, com resultado observado |

Erros: objeto tipado com `code`, `message`, `recoverable`, `suggested_action` e referência de diagnóstico redigida. Usar 404 para recurso ausente/fora do escopo, 409 para revisão/estado incompatível, 422 para pedido inválido e 503 para dependência indisponível. A UI não apresenta traceback como mensagem principal.

### DTOs mínimos

```typescript
type StageName = 'research' | 'script' | 'narration' | 'media' | 'editing' | 'review';
type Progress = {
  completed: number;
  total: number | null;
  unit: 'sources' | 'scenes' | 'segments' | 'shots' | 'frames' | 'bytes';
  source: string;
};
type ActionAvailability = {
  action: string;
  enabled: boolean;
  reason: string | null;
};
```

Os modelos completos vivem em `ui_backend/models.py`: `CapabilitiesView`, `ProfileView`, `ProductionView`, `StageView`, `ArtifactView`, `JobView`, `EventView`, `ActionRequest`, `OperationReceipt`, `MemoryView` e `ProblemView`. `ProductionView` inclui `mode: 'legacy' | 'staged'`, perfil/revisão quando conhecidos, estágios observáveis, artefatos, capacidades e cursor.

No legado, campos ausentes ficam nulos/indisponíveis. Não inventar um perfil ou seis estágios concluídos a partir de um MP4 encontrado em uma pasta.

## 8. Interfaces Python e integração com o domínio

```python
# ui_backend/app.py
create_app(settings: UiSettings, services: UiServices) -> FastAPI

# ui_backend/read_models.py
list_productions(filters: ProductionFilters, cursor: str | None) -> ProductionPage
get_production(production_id: str) -> ProductionView
get_stage(production_id: str, stage: StageName) -> StageView

# ui_backend/jobs.py — métodos de JobService
submit(request: ProductionRequest, *, idempotency_key: str) -> OperationReceipt
request_action(production_id: str, action: ActionRequest, *, idempotency_key: str) -> OperationReceipt
get_job(job_id: str) -> JobView

# ui_backend/events.py — métodos de EventService
snapshot_cursor(production_id: str) -> str
replay(production_id: str, after_cursor: str | None) -> list[EventView]
subscribe(production_id: str, after_cursor: str | None) -> AsyncIterator[EventView]

# ui_backend/artifacts.py — métodos de ArtifactService
resolve(artifact_id: str, *, production_id: str | None = None) -> ResolvedArtifact

# ui_backend/domain.py
get_capabilities() -> CapabilitiesView
execute_action(production_id: str, action: ActionRequest, control: RunControl) -> ProductionResult
```

`UiServices` agrupa consultas, jobs, eventos, artefatos e adaptador de domínio, injetáveis nos testes. `UiSettings` contém caminho raiz, banco de controle, bind/porta e diretório estático, sem chaves de provedores. `ProductionFilters`/`ProductionPage` incluem paginação validada; `ResolvedArtifact` inclui caminho já validado, tipo, tamanho e hash.

`RunControl` expõe `stop_requested() -> bool`, `report_progress(progress: ProgressUpdate) -> None` e `checkpoint(stage: StageName) -> None`. Acrescentar o argumento opcional ao `run_production` planejado, preservando chamadas existentes. O worker usa esse contrato; não depende de uma conexão HTTP ativa.

O adaptador de perfis chama `ProfileStore` do plano principal. O de memória chama consultas e operações versionadas já definidas, sem criar outro mecanismo de aprendizado. Ações ainda não implementadas retornam indisponibilidade estruturada; o frontend usa a razão para orientar o usuário.

`open_editor` fica limitado ao projeto pertencente à produção. Em modo bridge, pode simplesmente abrir/focar a integração configurada; não lançar múltiplas instâncias para o mesmo projeto automaticamente.

## 9. Arquivos propostos

### Backend e inicialização

| Arquivo novo | Responsabilidade |
|---|---|
| `src/ai_video_factory/ui_backend/models.py` | DTOs, ações, erros e eventos públicos |
| `src/ai_video_factory/ui_backend/app.py` | Composição FastAPI, lifespan e frontend estático |
| `src/ai_video_factory/ui_backend/routes.py` | Rotas finas, sessão e validação HTTP |
| `src/ai_video_factory/ui_backend/domain.py` | Adaptador para serviços de produção/perfil/memória |
| `src/ai_video_factory/ui_backend/read_models.py` | Consultas e projeção de manifests/bundles |
| `src/ai_video_factory/ui_backend/control_store.py` | SQLite de jobs, idempotência e eventos/projeções |
| `src/ai_video_factory/ui_backend/events.py` | Replay/stream e reconciliação de cursores |
| `src/ai_video_factory/ui_backend/jobs.py` | Submissão, fila, ações e estado de workers |
| `src/ai_video_factory/ui_backend/worker.py` | Entrada estruturada do processo de produção |
| `src/ai_video_factory/ui_backend/artifacts.py` | Entrega segura de artefatos e uploads |
| `src/ai_video_factory/ui_backend/session.py` | Bootstrap, cookie local, CSRF e redação |
| `src/ai_video_factory/ui_cli.py` | Comando de iniciar/abrir o painel |
| `scripts/build_ui.py` | Build/cópia dos assets para distribuição Python |
| `docs/interface-grafica.md` | Uso, recuperação, limitações e desenvolvimento |

Criar os `__init__.py` necessários. Modificar `cli.py`, `pyproject.toml`, `uv.lock`, `.gitignore`, README e, quando existir, o coordenador planejado. Assets gerados entram em `src/ai_video_factory/ui_static/` no artefato distribuído, sem manter outra cópia manual editável da UI.

### Frontend

```text
web/
  package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html
  src/
    main.tsx
    app/App.tsx, app/router.tsx, app/providers.tsx
    api/client.ts, api/events.ts, api/generated.ts, api/queryKeys.ts
    components/AppShell.tsx, StageList.tsx, ActivityFeed.tsx
    components/ArtifactViewer.tsx, StatusText.tsx, InlineError.tsx
    features/productions/ProductionList.tsx, ProductionCreate.tsx, ProductionWorkspace.tsx
    features/stages/ResearchView.tsx, ScriptView.tsx, NarrationView.tsx
    features/stages/MediaView.tsx, EditingView.tsx, ReviewView.tsx
    features/profiles/ProfileList.tsx, ProfileForm.tsx
    features/memory/MemoryList.tsx, LearningDetails.tsx
    features/tools/ToolsPage.tsx
    styles/tokens.css, styles/global.css
    test/setup.ts, test/handlers.ts
  e2e/production.spec.ts, profiles-memory.spec.ts, recovery.spec.ts
```

Criar testes junto às features/componentes, com `.test.tsx`; CSS Modules junto aos componentes quando necessário. Não importar código de composição de vídeo de `remotion/` para o painel. Compartilhar somente contratos explicitamente extraídos e estáveis, se surgir necessidade real.

## 10. Entregas progressivas e dependências do plano principal

| Entrega da interface | Dependência | O que já pode funcionar |
|---|---|---|
| **A — Monitor local** | RunStore e arquivos atuais | Listar execuções, ver estado/eventos observáveis, abrir artefatos e diagnosticar ferramentas |
| **B — Operação dos seis estágios** | Contratos/coordenador e runners do plano principal | Criar produção, acompanhar etapas reais, controlar parada/retomada e revisar entregas |
| **C — Perfis e memória** | ProfileStore e aprendizagem do plano principal | Editar perfil versionado, consultar regras/evidências e acompanhar mudanças autônomas |
| **D — FilmCraft e pacote final** | Cliente/editor/revisão do plano principal | Abrir projeto, acompanhar exportação, visualizar final e baixar pacote |

A interface não precisa esperar C/D para começar a ser útil. Dados de demonstração só existem em testes ou modo de demonstração claramente identificado; não são usados para preencher telas de produção vazias.

## 11. Tarefas de implementação

Executar cada tarefa com ciclo de teste de comportamento que falha, implementação mínima, verificação pertinente e commit focado. Os comandos são previstos para a execução futura; não foram executados ao escrever este plano.

### UI-1 — Contratos de consulta e adaptador de execuções existentes

**Arquivos:** criar `ui_backend/models.py`, `domain.py`, `read_models.py` e `tests/test_ui_read_models.py`.

**Interfaces:** produzir DTOs da seção 7 e consultas da seção 8; usar manifests/eventos públicos por um adaptador, sem expor métodos privados do RunStore como API.

- [x] Inventariar as alterações atuais de Windows e o estado real do plano principal antes de modificar código.
- [x] Escrever `test_legacy_run_is_shown_without_invented_profile`, `test_partial_jsonl_line_preserves_previous_events` e `test_unknown_stage_is_not_marked_completed`.
- [x] Executar `python -m pytest tests/test_ui_read_models.py -q` e confirmar falha inicial.
- [x] Implementar enumeração somente leitura dos diretórios/manifests conhecidos e projeção explícita do modo legado.
- [x] Reexecutar os testes e confirmar que consultar não escreve nem muda manifests; commit `feat: expose read models for production monitoring`.

**Entrega:** estado de produções legadas consultável sem depender dos módulos novos ainda ausentes.

### UI-2 — API local, sessão e escopo

**Arquivos:** criar `ui_backend/app.py`, `routes.py`, `session.py`, `tests/test_ui_api.py` e `tests/test_ui_session.py`; ajustar extra `ui` em `pyproject.toml`/lock.

**Interfaces:** produzir `create_app`, rotas read-only, bootstrap e `CapabilitiesView`; serviços injetáveis.

- [x] Escrever testes de snapshot/capacidades, perfil inexistente, acesso cruzado de perfil e rejeição de Host/Origin inesperados.
- [x] Testar bootstrap de uso único, cookie de sessão, proteção de mutações e ausência de segredos nos DTOs/logs.
- [x] Executar `python -m pytest tests/test_ui_api.py tests/test_ui_session.py -q`; confirmar falha inicial.
- [x] Implementar API e instalar FastAPI/Uvicorn apenas no extra `ui`, preservando o uso do CLI sem esse extra.
- [x] Confirmar contratos HTTP e resposta útil sem frontend compilado; commit `feat: add a local authenticated UI API`.

**Entrega:** servidor consultável de forma consistente e com fronteira local definida.

### UI-3 — Journal de eventos, snapshots e reconexão SSE

**Arquivos:** criar `control_store.py`, `events.py` e `tests/test_ui_events.py`.

**Interfaces:** implementar `EventService` e cursor de snapshot; consumir manifests/eventos da UI-1.

- [x] Escrever `test_reconnect_replays_only_events_after_cursor`, `test_duplicate_event_is_not_inserted_twice` e `test_expired_cursor_requires_new_snapshot`.
- [x] Testar que um evento ocorrido entre snapshot e assinatura é recebido, que uma linha incompleta não corrompe o cursor e que o encerramento da conexão libera recursos.
- [x] Executar `python -m pytest tests/test_ui_events.py -q`; confirmar falha inicial.
- [x] Implementar IDs persistidos, replay, reconciliação e fluxo SSE. Mensagens de heartbeat mantêm conexão sem fingir avanço de produção.
- [x] Reexecutar testes e medir o número de consultas/arquivos lidos numa sequência longa de eventos; commit `feat: stream resumable production events to the UI`.

**Entrega:** atualização confiável que converge depois de desconexão.

### UI-4 — Jobs persistentes e controles cooperativos

**Arquivos:** criar `jobs.py`, `worker.py`, `tests/test_ui_jobs.py` e `tests/test_ui_worker.py`; estender o coordenador planejado com `RunControl` quando disponível.

**Interfaces:** produzir `JobService`, `OperationReceipt` e hook da seção 8; consumir `run_production` do plano principal. A capacidade de iniciar o fluxo novo fica desabilitada até essa dependência existir.

- [x] Escrever `test_same_idempotency_key_launches_one_worker`, `test_api_restart_does_not_relaunch_running_job` e `test_browser_disconnect_does_not_stop_worker`.
- [x] Testar fila com uma produção ativa, cancelamento de job ainda na fila, parada solicitada no meio de uma etapa e confirmação somente em checkpoint seguro.
- [x] Testar falha de lançamento após persistência e crash após aplicação externa: reconciliar; não assumir que PID existente prova o mesmo worker.
- [x] Executar `python -m pytest tests/test_ui_jobs.py tests/test_ui_worker.py -q`; confirmar falha inicial.
- [x] Implementar claim transacional/lease, spawn sem shell/sem janela extra no Windows, heartbeat e resultado persistido.
- [x] Testar que duas abas não iniciam o mesmo pedido duas vezes e que retomar usa a mesma produção; commit `feat: run durable production jobs behind UI controls`.

**Entrega:** tarefas longas independentes da conexão do navegador.

### UI-5 — Shell React, tokens e contratos gerados

**Arquivos:** criar `web/` com Vite/React/TypeScript, componentes base, estilos, testes e `api/generated.ts`; documentar geração OpenAPI.

**Interfaces:** API tipada gerada a partir dos DTOs; router com produções, perfis, memória e ferramentas.

- [x] Criar teste `App.test.tsx` cobrindo navegação por teclado e estado vazio com ação “Nova produção”.
- [x] Configurar scripts `dev`, `build`, `typecheck`, `lint`, `test`, `test:e2e` e `generate:api`; fixar dependências e lockfile.
- [x] Executar o teste e confirmar que falha antes da composição do shell.
- [x] Implementar layout, três tamanhos tipográficos, tokens, foco e erro global. Não conectar dados fictícios ao modo normal.
- [x] Executar `npm run typecheck`, `npm test -- --run` e `npm run build` em `web/`; commit `feat: scaffold the local production dashboard`.

**Entrega:** estrutura navegável e consistente, pronta para dados reais.

### UI-6 — Lista, criação e preflight de produção

**Arquivos:** implementar features `productions/`, `api/client.ts`, `queryKeys.ts` e testes de lista/criação.

**Interfaces:** consumir endpoints de perfis, preflight, produções e receipts; ler `ActionAvailability`.

- [x] Testar lista com filtros, vazio sem dados e erro com retry; a chave de cache inclui perfil e filtros.
- [x] Escrever `test_double_submit_uses_same_idempotency_key` e `test_profile_switch_does_not_show_previous_profile_results`.
- [x] Testar preflight impedindo ação indisponível e execução parcial permitida até uma etapa disponível.
- [x] Executar os testes da feature para confirmar falha; implementar formulário e navegação para a produção criada.
- [x] Verificar salvar rascunho sem executar, mensagem de pendência e prevenção de cliques repetidos; commit `feat: create and filter productions from the dashboard`.

**Entrega:** operação inicial sem exigir uso do terminal.

### UI-7 — Área de produção e progresso real

**Arquivos:** implementar `ProductionWorkspace.tsx`, `StageList.tsx`, `ActivityFeed.tsx`, `api/events.ts` e testes correspondentes.

**Interfaces:** snapshot + cursor, SSE e DTOs de progresso; cache invalidado/atualizado por perfil/produção.

- [x] Escrever `test_unknown_total_has_no_percentage`, `test_stage_count_is_not_time_percentage` e `test_reconnect_converges_to_latest_snapshot`.
- [x] Testar perda de conexão preservando dados com aviso; evento de outra produção não altera a tela atual.
- [x] Testar erro persistente da etapa, ação de retomada habilitada por capacidade e seleção de etapa preservada durante eventos.
- [x] Executar testes, implementar atualização incremental e fallback de consulta com backoff.
- [x] Verificar teclado, foco, rolagem do histórico e redução de movimento; commit `feat: show live six-stage production progress`.

**Entrega:** resposta clara sobre etapa atual, atividade, resultado e pendências.

### UI-8 — Inspetores de pesquisa, roteiro, áudio e mídia

**Arquivos:** implementar os quatro primeiros inspetores, `ArtifactViewer.tsx`, `artifacts.py`, rotas de arquivos/upload e `tests/test_ui_artifacts.py`.

**Interfaces:** consumir bundles do plano principal, manifesto de artefatos e endpoints por ID; exibir indisponibilidade para bundle ainda ausente.

- [x] Testar fonte/afirmação com evidência, roteiro com fala e direção separadas, player por segmento e licença da mídia.
- [x] Testar conteúdo Markdown com HTML/script como texto seguro e arquivo de outro perfil inacessível.
- [x] Escrever `test_artifact_range_returns_partial_content` e `test_artifact_symlink_outside_root_is_rejected`; cobrir diretório com espaços e junction/link no Windows quando suportado pelo teste.
- [x] Testar upload interrompido removendo somente seu parcial, tipo/tamanho inválidos e hash registrado.
- [x] Executar `python -m pytest tests/test_ui_artifacts.py -q` e testes React antes/depois da implementação.
- [x] Verificar visualização de mídia grande sem converter para base64; commit `feat: inspect sources scripts narration and licensed media`.

**Entrega:** usuário consegue avaliar os materiais antes de chegar ao vídeo final.

### UI-9 — FilmCraft, revisão, retrabalho e exportação

**Arquivos:** implementar `EditingView.tsx`, `ReviewView.tsx`, ações de domínio e `tests/test_ui_actions.py`.

**Interfaces:** endpoints de ações chamam serviços reais de edição/revisão e retornam jobs; usar versão esperada para salvar correções.

- [x] Testar projeto indisponível e projeto válido abrindo pela operação permitida, nunca por shell recebido do browser.
- [x] Testar aviso de mídia offline impedindo indicação de entrega final e exportação com encoder real informado.
- [x] Escrever `test_stop_request_is_not_reported_as_completed_cancellation`; a tela permanece “Parada solicitada” até confirmação do worker.
- [x] Testar edição de roteiro com comparação/impacto e substituição de mídia invalidando somente dependentes corretos.
- [x] Testar pacote íntegro disponível para download e ausência de upload/publicação automática.
- [x] Executar testes React e `python -m pytest tests/test_ui_actions.py -q`; commit `feat: review FilmCraft exports and request targeted rework`.

**Entrega:** edição externa e revisão visíveis, com ações que correspondem ao estado real.

### UI-10 — Perfis e memória autônoma visíveis

**Arquivos:** implementar features `profiles/` e `memory/`, adaptadores de API e `tests/test_ui_profiles_memory.py`.

**Interfaces:** usar `ProfileStore`, feedback e consultas de memória do plano principal. Sem domínio disponível, habilitar só o que pode ser consultado com segurança.

- [x] Testar criação/edição, campos herdados, revisão concorrente 409 e explicação de que produções em curso mantêm seu snapshot.
- [x] Testar separação de dados/cache entre canais e candidato/hipótese distinguido de regra ativa.
- [x] Testar evento de aprendizagem automática atualizando a lista sem pedir aprovação humana.
- [x] Testar detalhe com evidência e antes/depois; suspensão manual opcional usa o serviço versionado.
- [x] Executar testes React e `python -m pytest tests/test_ui_profiles_memory.py -q` antes/depois da implementação.
- [x] Confirmar que segredos não são campos renderizados e que instrução explícita é distinguível de inferência; commit `feat: manage channel profiles and inspect autonomous memory`.

**Entrega:** configurações e aprendizado deixam de ficar escondidos em arquivos.

### UI-11 — Diagnóstico, launcher e distribuição local

**Arquivos:** implementar `ToolsPage.tsx`, `ui_cli.py`, `scripts/build_ui.py`, documentação e `tests/test_ui_launcher.py`; ajustar `cli.py`, `pyproject.toml`, lock, README e arquivos estáticos de distribuição.

**Interfaces:** comando novo proposto `ai-video-factory ui`; abre painel servido pelo próprio Python, com opção `--no-browser` e porta configurável.

- [x] Testar CLI sem extra instalado exibindo instrução clara, porta ocupada sem matar processo alheio e detecção de instância já existente.
- [x] Testar build/cópia de assets com manifesto, wheel contendo os arquivos necessários e fallback de rota para navegação direta.
- [x] Testar ferramenta instalada/não configurada e teste de conexão disparado somente pela ação do usuário.
- [x] Executar `python -m pytest tests/test_ui_launcher.py -q`; confirmar falha inicial.
- [x] Implementar launcher sem criar produção, iniciar editor ou abrir janelas extras; reaproveitar `.venv` e o iniciador Windows atual quando apropriado.
- [x] Verificar execução da UI compilada sem servidor Node, comandos legados preservados e ausência de arquivos CDN; commit `feat: launch and distribute the local video factory UI`.

**Entrega:** abrir a interface passa a ser uma operação simples e documentada.

### UI-12 — Integração, acessibilidade e piloto de uso

**Arquivos:** criar E2E em `web/e2e/`, `tests/test_ui_integration.py` e relatório em `docs/interface-grafica.md`.

**Interfaces:** consumir aplicação real com domínio/transportes controlados; teste real de FilmCraft separado dos testes normais.

- [x] Executar jornadas E2E: criar produção, acompanhar seis etapas, inspecionar artefatos, corrigir uma etapa e ver a retomada.
- [x] Testar duas abas, queda/reconexão SSE, refresh, fechamento da aba e reinício da API enquanto worker continua.
- [x] Testar dois perfis com a mesma mídia e memórias diferentes; interface/API não misturam resultados.
- [x] Testar player com vídeo longo, seek/Range e arquivo ausente; nenhuma leitura integral em memória no serviço.
- [x] Verificar acessibilidade automática e manual: teclado, foco, contraste, anúncios de estado sem excesso e movimento reduzido.
- [x] Revisar screenshots a 1440px, 1024px, 768px e 390px; corrigir hierarquia, overflow e estados vazios/erros.
- [x] Executar builds/testes do escopo e uma jornada com produção real configurada; registrar falhas e limitações observadas.
- [x] Commit `test: verify dashboard recovery accessibility and real production flow`.

**Entrega:** interface utilizável no ambiente real, com evidência de recuperação e consistência.

## 12. Marcos de entrega

| Marco | Tarefas | Resultado verificável |
|---|---|---|
| UI-M0 — Monitor read-only | UI-1, UI-2, UI-3, UI-5 e parte read-only de UI-7/UI-8 | Abrir execuções atuais, ver eventos/artefatos e reencontrar estado após refresh |
| UI-M1 — Produção operável | UI-4, UI-6 e conclusão de UI-7 | Iniciar/retomar fluxo novo quando domínio disponível; produção independente da aba |
| UI-M2 — Entregas e revisão | UI-8, UI-9 | Inspecionar fontes, roteiro, voz, mídia, FilmCraft e pacote |
| UI-M3 — Perfis e memória | UI-10 | Editar perfil e acompanhar mudanças autônomas com evidência |
| UI-M4 — Uso local completo | UI-11, UI-12 | Launcher, distribuição, acessibilidade, recuperação e piloto |

Dependências técnicas: UI-1 -> UI-2 -> UI-3; UI-2 -> UI-4; UI-2 -> UI-5; UI-4/UI-5 -> UI-6; UI-3/UI-5 -> UI-7; UI-2/UI-5 -> UI-8; UI-4/UI-8 -> UI-9; UI-2/UI-5 e domínio de perfis -> UI-10; UI-2/UI-5 -> UI-11; UI-6–UI-11 -> UI-12.

UI-M0 pode ser entregue sem implementar todo o plano principal. A habilitação de criar perfis, editar memórias e operar os seis estágios exige que suas tarefas de domínio estejam concluídas. Não mudar esses critérios para preencher um marco com telas falsas.

## 13. Verificação prevista

Executar no ambiente de implementação, com dependências de teste instaladas. Scripts frontend citados devem ser criados na UI-5.

```powershell
# Backend, na raiz do repositório.
python -m pytest tests/test_ui_read_models.py tests/test_ui_api.py tests/test_ui_session.py -q
python -m pytest tests/test_ui_events.py tests/test_ui_jobs.py tests/test_ui_worker.py -q
python -m pytest tests/test_ui_artifacts.py tests/test_ui_actions.py tests/test_ui_profiles_memory.py -q
python -m pytest tests/test_ui_launcher.py tests/test_ui_integration.py -q

# Frontend, dentro de web/.
npm ci
npm run generate:api
npm run typecheck
npm run lint
npm test -- --run
npm run build
npm run test:e2e
```

A geração de tipos usa OpenAPI produzido pela app factory com serviços de teste/offline, sem exigir modelo, editor ou credenciais. Comparar saída gerada com o arquivo versionado para detectar drift de contrato.

Rodar regressões Python existentes dos módulos alterados e a suíte completa no marco de integração, registrando falhas preexistentes separadamente. Não declarar que o projeto inteiro está passando se apenas os testes da GUI passaram. Remotion só precisa ser reconstruído/testado se um contrato compartilhado seu for alterado.

## 14. Checklist de aceitação

- [x] Usuário consegue abrir a interface sem conhecer comandos internos do pipeline.
- [x] Tela inicial mostra produções reais e distingue legado de fluxo novo.
- [x] Cada produção identifica canal/perfil e snapshot utilizado quando conhecidos.
- [x] Os seis estágios apresentam estado, entregas e pendências reais.
- [x] Progresso com unidade/total conhecido; ausência de dado não gera percentual inventado.
- [x] Fontes, roteiro, voz, mídia, prévia, vídeo final e pacote podem ser inspecionados.
- [x] Fechar/atualizar a aba não encerra o worker e não duplica a produção.
- [x] Reconexão e reinício da API convergem para o estado real.
- [x] Duas abas e retries respeitam idempotência e revisão esperada.
- [x] Parada solicitada permanece pendente até confirmação em ponto seguro.
- [x] Correção de insumo provoca invalidação/retrabalho somente do que depende dele.
- [x] Perfis e memórias não se misturam no backend nem no cache frontend.
- [x] Aprendizados automáticos ficam visíveis sem uma aprovação humana obrigatória.
- [x] Arquivos grandes podem ser reproduzidos e buscados no player por Range.
- [x] Mídia offline, configuração ausente e conteúdo parcial são comunicados honestamente.
- [x] Segredos não aparecem em DTOs, URLs de mídia, logs ou arquivos exportados da UI.
- [x] UI é utilizável por teclado e sem depender apenas de cor.
- [x] Build estático é servido pelo Python, preservando CLI e suporte Windows existentes.
- [x] Nenhuma ação do painel publica vídeos automaticamente.
- [x] Relatório final registra validação, falhas preexistentes e capacidades ainda indisponíveis.

## 15. Fora do escopo e decisões posteriores

- Editor de vídeo próprio, timeline completa no browser ou substituição da interface do FilmCraft.
- Hospedagem pública, contas de equipe, acesso remoto, nuvem e sincronização entre computadores.
- Empacotamento Tauri/Electron e instalador independente antes de validar a aplicação web local.
- Dashboard de monetização/CTR/retenção sem uma fonte de dados real integrada.
- Calibração fina de voz, montagem ou aprendizado; a GUI expõe configurações tipadas que o domínio já suportar.
- Chatbot como navegação principal, canvas de automação visual e configuração livre de scripts pelo usuário.
- Seleção de nicho ou idioma definitivo do primeiro canal.
- Controle de tarefas de implementação do software; os marcos deste documento continuam no plano, não viram produções de vídeo.

### Revisão do plano

- [x] Confirmar que a interface estava adiada no plano principal.
- [x] Escolher linguagem e justificar arquitetura sem reescrever o backend.
- [x] Definir telas, jornadas, estados e direção visual.
- [x] Conectar monitoramento a estado/eventos reais, com recuperação e idempotência.
- [x] Integrar perfis e memória preservando autonomia por canal.
- [x] Separar capacidades disponíveis das dependências futuras do plano principal.
- [x] Definir arquivos, interfaces, testes e marcos de entrega.
- [x] Implementar e verificar o produto. Este item não é concluído pela criação do plano.

