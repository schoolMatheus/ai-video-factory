# AI Video Factory — Estágios, perfis com memória e FilmCraft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:subagent-driven-development only if delegation is chosen for execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o fork para produzir vídeos longos horizontais em seis estágios independentes, coordenados por perfis de canal com memória persistente e aprendizado autônomo, usando FilmCraft via MCP na edição.

**Architecture:** Um novo coordenador conecta pesquisa, roteiro, narração, mídia, edição e revisão por contratos versionados e artefatos persistidos. O RunStore existente continua responsável pela execução e retomada; um armazenamento de perfis e memória acrescenta contexto por canal, evidências e versões. O FilmCraft recebe a montagem por um adaptador MCP, sem exigir outro servidor MCP de edição.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, SQLite da biblioteca padrão, JSON/Markdown para artefatos, FFmpeg/ffprobe para inspeção e preparação de mídia, adaptadores de LLM/TTS, FilmCraft e cliente MCP opcional. Preservar Remotion/FFmpeg existentes durante a migração.

**Spec:** Este documento é autocontido: a [especificação consolidada](#1-resultado-esperado) nas seções 1–9 registra o escopo acordado e as decisões técnicas propostas; as seções 10–14 detalham a implementação e sua aceitação.

**Data:** 23 de novembro de 2026.

**Estado:** Plano para revisão e execução posterior. Nenhuma funcionalidade descrita como nova está implementada por este documento.

## Global Constraints

- Python: manter `>=3.12,<3.13`, conforme `pyproject.toml`, durante esta atualização.
- Formato proposto para o primeiro perfil: 1920×1080, 16:9, 30 fps; duração de produção configurável entre 20 e 30 minutos, inicialmente 25 minutos. São padrões técnicos propostos, não decisões editoriais confirmadas pelo usuário.
- Idioma, nicho e nome do primeiro canal continuam por definir. Catolicismo foi um exemplo, não o canal definitivo.
- A pesquisa deve partir do tema informado. Descoberta de tendências é opcional e não pode substituir esse tema silenciosamente.
- O roteiro detalhado antecede a narração; a duração real do áudio governa o tempo final da montagem.
- Cada perfil tem memória própria nos seis estágios. Compartilhamento entre canais exige uma operação explícita.
- O agente pode revisar, avaliar e aplicar aprendizados sozinho; não solicitar aprovação humana para cada ajuste de memória.
- Preferências explícitas do usuário prevalecem sobre preferências inferidas. Autonomia não autoriza mudar o objetivo editorial do canal.
- Preservar versões, evidências e reversão das mudanças automáticas.
- Não calibrar agora pesos, limites de desempenho, volume de música, velocidade da voz ou limiares de confiança. Representar esses ajustes como políticas configuráveis, a serem refinadas depois.
- A autonomia de memória não altera a política existente de aprovação de publicação. O fluxo novo termina com um pacote para revisão/publicação posterior; não faz upload automaticamente.
- Não baixar modelos, instalar editor, configurar credenciais, criar agendamentos ou alterar o sistema operacional como parte da escrita deste plano.
- O fluxo novo deve operar no Windows nativo; WSL pode ser documentado como alternativa, sem ser uma dependência escondida.
- Preservar os contratos públicos e testes dos fluxos antigos enquanto o fluxo novo é validado.

## Review Focus

1. Dois canais usando a mesma mídia: uma rejeição editorial em um perfil não deve bloquear a mídia no outro. Cobertura: tarefas 4 e 10.
2. Queda depois de uma alteração no editor e antes do registro local: a retomada deve reconciliar o projeto, sem duplicar clipes. Cobertura: tarefas 11 e 12.
3. Mudança automática de perfil durante uma produção: a produção continua com a versão fixada; a nova versão vale para próximas produções. Cobertura: tarefas 3, 5 e 14.
4. Edição manual no FilmCraft: o estado observado deve ser comparado com o anterior; ações não observadas não podem ser inventadas. Cobertura: tarefas 12 e 14.
5. Fonte contraditória, licença incompleta ou mídia offline: o sistema registra a pendência e não trata exportação bem-sucedida como validação do conteúdo. Cobertura: tarefas 7, 10 e 13.

---

## 1. Resultado esperado

O operador escolhe um perfil, informa um tema e inicia uma produção. O sistema pesquisa, escreve um roteiro de direção, produz a narração, seleciona materiais, monta no FilmCraft e entrega o vídeo com relatórios e arquivos de publicação.

Cada etapa pode ser inspecionada, corrigida e retomada. Cada agente recebe contexto do perfil, trabalha sobre entregas explícitas e registra resultados na memória. O perfil aprende automaticamente com falhas, correções, avaliações e resultados disponíveis, sem apagar o histórico.

Um agente, neste plano, é uma responsabilidade com entrada, saída e ferramentas delimitadas. Os agentes podem compartilhar o mesmo modelo de linguagem e executar sequencialmente. Não é necessário criar chats ou processos de IA separados para cada estágio.

### Decisões já dadas pelo usuário

- Organizar o processo em estágios com entregas suficientemente detalhadas para outro agente continuar.
- Fazer pesquisa aprofundada e reunir fontes antes de elaborar o roteiro.
- Escrever o que será falado e mostrado, incluindo pausas e instruções de direção.
- Gerar a voz em software de narração a partir desse roteiro.
- Buscar imagens e clipes e usar um editor externo para a montagem.
- Usar FilmCraft, da ArtCraft, com sua integração MCP nativa.
- Criar perfis com memória específica de canal/nicho em todos os estágios.
- Permitir que o agente aplique aprendizados automaticamente.
- Deixar os ajustes finos de avaliação e parametrização para uma etapa posterior.

### Decisões técnicas propostas neste plano

- Novo fluxo opt-in, com seis estágios e adaptadores para aproveitar os módulos existentes.
- SQLite para perfis, versões e aprendizado; arquivos para mídias e entregas de agentes.
- Contrato editorial novo, separado do `EditDocument` legado.
- FilmCraft inicialmente em modo bridge, permitindo acompanhar o projeto aberto; headless é uma evolução posterior do mesmo adaptador.
- Implementação por marcos, preservando o fluxo antigo até o piloto final passar.

## 2. Diagnóstico do código atual

Base examinada: checkout local do fork `schoolMatheus/ai-video-factory`, revisão `fc4388b`. Os caminhos citados são relativos à raiz do repositório. A leitura não substitui uma execução completa.

| Área | Evidência atual | Consequência para a atualização |
|---|---|---|
| Coordenação | `video_pipeline.py`, `daily_job.py`, `scheduler.py` e `nightly_batch.py` oferecem caminhos distintos | Criar uma coordenação comum para o novo fluxo e adaptar os comandos progressivamente |
| Pesquisa | `research_pipeline.py` tem conteúdo persistido, afirmações e evidências; `video_pipeline.py` ainda usa pesquisa de tendências diretamente | O novo estágio usa pesquisa sobre o tema e conteúdo real das fontes |
| Roteiro | `longform.py`, `script_generator.py`, `formats.py`, `duration_enforcer.py` | Reutilizar formatos e geração por partes, preservando evidências e direção em contrato próprio |
| Voz | `narration.py` tem Kokoro/Piper/espeak; padrões e caminhos de voz são centrados em inglês/Linux | Extrair interface de TTS, declarar suporte de idioma e evitar degradação silenciosa |
| Mídia | `stock_providers.py`, `stock_media.py`, `nasa_media.py`, `assets.py`, `asset_qc.py` | Reaproveitar provedores e QC; acrescentar múltiplos planos, adequação contextual e mapa por cena |
| Memória existente | `asset_memory.py` guarda rejeições em um arquivo global por padrão | Separar rejeição técnica de rejeição editorial e acrescentar escopo de perfil |
| Retomada | `run_store.py` registra entradas, eventos e integridade dos artefatos | Incluir versão/configuração efetiva do perfil nas entradas de cada etapa |
| Esquema de edição | `EditDocument`/`EditScene` são estritos e não preservam todos os campos editoriais necessários | Não inserir campos arbitrários nem depender do builder que ignora campos desconhecidos |
| Renderização | `RenderEngine` em `production.py` mistura síntese da voz e render; há Remotion/FFmpeg | No fluxo novo, separar narração da edição; usar adaptador explícito para o legado |
| Plataforma | `video_pipeline.py` e `scheduler.py` importam `fcntl`; há caminhos Unix para executáveis e fontes | Corrigir a fronteira de plataforma antes da integração no Windows |
| Formato final | `_polish_master` recorta/redimensiona para proporção mais larga | O novo fluxo valida 1920×1080 e não aplica esse pós-processamento automaticamente |
| Publicação | Há `publisher.py`, `youtube.py` e revisão | Reutilizar empacotamento sem modificar a autorização de publicação |

Não tratar relatórios antigos de falhas como prova de bugs ainda presentes: alguns problemas já possuem correções no código atual. A linha de base deve ser medida novamente no início da execução.

`production.py` também contém limites legados para produções de 15–20 minutos. O novo fluxo deve usar a duração resolvida do perfil, sem importar esses limites fixos para um episódio de 25 minutos. Preservar o comportamento legado enquanto ele continuar sendo usado.

## 3. Arquitetura e organização dos estágios

```text
perfil escolhido + tema
        |
        v
snapshot do perfil + contexto de memória por estágio
        |
        v
1 pesquisa -> 2 roteiro -> 3 narração -> 4 mídia -> 5 FilmCraft -> 6 revisão/pacote
        |           |           |          |            |             |
        +-----------+-----------+----------+------------+-------------+
                                |
                       observações persistidas
                                |
                 revisão automática dos aprendizados
                                |
             avaliar -> ativar/suspender -> nova versão do perfil
                                |
                      próximas produções
```

### Responsabilidades transversais

- **Coordenador:** resolve dependências, cria contexto, chama o estágio e persiste o resultado.
- **RunStore:** estado de execução, tentativas, entradas, eventos e integridade dos artefatos.
- **ProfileStore:** identidade, configurações explícitas, revisões, observações e aprendizados.
- **Contexto de memória:** seleção das regras e exemplos relevantes para um estágio, com referências às evidências.
- **Avaliador de aprendizagem:** decide se uma proposta atende à política e às verificações aplicáveis.
- **Adaptadores:** encapsulam modelos, TTS, provedores de mídia e FilmCraft.

Evitar uma reescrita geral de `video_pipeline.py`. O novo fluxo tem uma entrada própria; módulos existentes são adaptados por suas interfaces úteis.

## 4. Contratos de entrega e artefatos

Todos os modelos novos usam Pydantic com `schema_version=1`, validação estrita e identificadores persistentes. A versão 1 é do contrato novo, não uma alteração silenciosa do esquema legado.

### Estrutura de produção proposta

```text
data/
  profiles/profiles.sqlite3
  projects/<profile_id>/<production_id>/
    production.json
    profile_snapshot.json
    state/
    artifacts/
      01_research/
      02_script/
      03_narration/
      04_media/
      05_editing/
      06_review/
    memory/decisions.jsonl
    package/
```

`artifacts/` é a raiz de integridade do RunStore desta produção; arquivos que os estágios declaram como entregas devem estar dentro dela. Projetos que referenciam mídias externas precisam de um manifesto adicional de dependências e hashes; salvar apenas o projeto do editor não comprova integridade da montagem.

SQLite é a fonte canônica de perfis e memória. JSON/Markdown exportados são consultas ou snapshots, não uma segunda configuração concorrente. O histórico técnico do RunStore continua canônico para suas execuções; a memória referencia seus identificadores e artefatos.

### Modelos novos e campos mínimos

| Modelo | Campos obrigatórios ou semanticamente necessários |
|---|---|
| `ProductionRequest` | `production_id`, `profile_id`, `topic`, `angle`, `target_minutes`, `seed_source_urls`; idioma e ferramentas resolvidos do perfil |
| `ProfileSnapshot` | `profile_id`, `revision`, `settings`, `explicit_fields`, `active_learning_ids`, `settings_digest`; sem credenciais |
| `ArtifactRef` | `path`, `sha256`, `size_bytes`, `media_type`; caminhos resolvidos relativos à produção |
| `StageContext` | pedido, snapshot fixado, estágio, tentativa, diretório de artefatos, resumo da memória e referências |
| `ResearchBundle` | tema, recorte, fontes, conteúdo persistido, afirmações, evidências, contradições, incertezas e síntese |
| `ScriptBundle` | título, capítulos, cenas, planos, fala exata, pausas, intenções, textos na tela, referências de afirmações e duração estimada |
| `NarrationBundle` | provedor/voz efetivos, idioma, segmentos por cena, texto falado, áudio, durações medidas e marcações de tempo |
| `MediaBundle` | candidatos e escolhidos por plano, consultas, arquivos, intervalos de origem, direitos, atribuição e lacunas |
| `AssemblyPlan` | resolução/fps, faixas, itens com tempos racionais, mídia de origem, narração, textos, legendas, transições e intenção de áudio |
| `EditingBundle` | versão do FilmCraft, modo, projeto, mapa de itens, plano aplicado, estado inspecionado, prévia, exportação e avisos |
| `ReviewBundle` | verificações medidas, revisão editorial, direitos, falhas, encaminhamento de correções, status e pacote |
| `StageResult` | estágio, estado, referências de artefatos, observações, configuração efetiva e erro estruturado quando houver |

Cada cena tem `scene_id` estável e vários planos com `shot_id`. As referências entre roteiro, voz, mídia e montagem usam esses IDs, nunca apenas a posição na lista. O resumo editorial distingue fato sustentado, alegação atribuída, tradição, interpretação e hipótese quando essas categorias forem pertinentes ao tema.

O roteiro é a fonte do conteúdo falado. Normalização de pronúncia não autoriza o agente de voz a acrescentar ou remover conteúdo. Alterações editoriais voltam ao estágio 2 e invalidam as dependências afetadas.

### Estados e dependências

Execução: `pending`, `running`, `completed`, `failed`, `superseded`, mantendo os estados do RunStore. Pendências editoriais aparecem no resultado do estágio, sem inventar um estado incompatível no manifest legado.

Dependências: pesquisa -> roteiro -> narração -> mídia -> edição -> revisão. Mídia também depende do roteiro; revisão consulta todas as entregas. Aprendizagem é transversal e não se torna um sétimo estágio obrigatório antes de produzir.

Uma alteração de música invalida a montagem e a revisão afetadas, não a pesquisa. Mudança factual no roteiro invalida as falas e montagens dependentes. O plano de invalidação usa digests de entradas relevantes por estágio, não a data ou a revisão global do banco.

Guardar a revisão global do perfil nos metadados de auditoria, separada da chave de reutilização. Incluir indiscriminadamente essa revisão no fingerprint de toda etapa anularia a invalidação seletiva. Dentro de uma produção, o snapshot fixado e seus IDs de aprendizagem devem continuar resolvíveis mesmo depois de uma regra ser substituída no perfil atual.

## 5. Definição dos seis estágios

### Estágio 1 — Pesquisa aprofundada e dossiê

**Entrada:** tema e recorte, perfil, fontes iniciais opcionais e contexto de memória de pesquisa.

**Processamento:** formular subquestões; descobrir fontes no tema; obter conteúdo real; classificar e comparar fontes; extrair afirmações com trechos de evidência; registrar divergências; produzir uma síntese para o roteirista. Reutilizar o modo de produção de `research_pipeline.py`; nunca classificar um texto como sustentado apenas porque sua URL responde.

**Saída:** `sources.json`, conteúdo das fontes, `claims.json`, `contradictions.json`, `verified_facts.json`, `research_bundle.json` e `research_brief.md`.

**Critério para avançar:** material sustentado suficiente para o recorte e pendências explicitadas. Insuficiência deve provocar nova pesquisa limitada pela política ou falha informativa; não preencher duração com invenção. Quantidade ideal de fontes e profundidade ficam configuráveis para calibração posterior.

**Memória:** utilidade contextual das fontes, falhas de acesso, lacunas recorrentes e correções. Falha transitória de rede não vira proibição editorial permanente.

### Estágio 2 — Roteiro de fala e direção

**Entrada:** dossiê, perfil e memória editorial.

**Processamento:** construir abertura, desenvolvimento e conclusão; elaborar capítulos; escrever fala exata; planejar pausas e intenção; detalhar cada cena e seus planos; informar o que mostrar e por quê; vincular afirmações a fontes; estimar duração. Aproveitar geração por partes e presets existentes, mas não tomar número de palavras como comprovação da duração final.

**Saída:** `script_bundle.json`, `script.md`, plano visual por cena/plano e texto canônico de narração.

**Critério para avançar:** nenhuma referência quebrada, fala e direção separadas, coerência com o tema e cada afirmação factual verificável ligada ao dossiê. Direção visual pode marcar lacunas para o estágio 4, sem fingir que a mídia já foi encontrada.

**Memória:** estruturas, correções, exemplos e preferências do canal. Templates não devem tornar episódios repetitivos nem se sobrepor ao conteúdo pesquisado.

### Estágio 3 — Narração em software de voz

**Entrada:** texto canônico e instruções do roteiro, perfil de voz e pronúncias aprendidas.

**Processamento:** preparar texto falável preservando o significado; selecionar provedor habilitado; sintetizar por cena/segmento; medir áudio; revisar omissões, silêncio, clipping e pronúncia conforme capacidades disponíveis; obter alinhamento quando configurado. Registrar se o tempo é exato por palavra ou apenas por segmento.

**Saída:** WAV por segmento, `narration_bundle.json`, texto efetivamente falado e marcações de tempo. Faixa contínua é derivada, não a única cópia da narração.

**Critério para avançar:** áudio real disponível no idioma escolhido, correspondência com o roteiro e tempos medidos. Não trocar silenciosamente uma voz aprovada por voz de baixa qualidade em outro idioma.

**Memória:** pronúncias contextuais, voz/provedor/modelo efetivos, pausas e resultados. Os valores finos de ritmo serão ajustados posteriormente.

### Estágio 4 — Busca, seleção e preparação de mídia

**Entrada:** planos do roteiro, tempos reais da voz e memória visual.

**Processamento:** derivar consultas adequadas aos provedores, inclusive em outro idioma quando útil; buscar candidatos; verificar qualidade técnica, direitos e adequação; selecionar vários planos por cena quando necessário; determinar intervalos e movimentos em imagens; registrar repetições e alternativas. Reutilizar provedores existentes e permitir arquivos próprios.

**Saída:** `media_bundle.json`, arquivos locais, direitos/atribuições e relatório de lacunas. Cada plano aponta para um arquivo ou uma estratégia explícita e verificável de composição.

**Critério para avançar:** toda mídia necessária presente e com direitos documentados; material ilustrativo não apresentado como registro específico; lacunas essenciais bloqueiam a montagem final. Uma prévia pode mostrar lacunas identificadas, sem ser classificada como entrega final.

**Memória:** consultas úteis, rejeições contextuais, repetição e referências visuais. Corrupção de arquivo pode gerar registro técnico compartilhado; inadequação editorial permanece no perfil.

### Estágio 5 — Montagem e edição no FilmCraft

**Entrada:** roteiro, voz, mídia, plano de montagem e contexto de edição.

**Processamento:** conectar ao MCP nativo; inspecionar versão e catálogo; abrir/criar projeto; importar mídia; montar faixas; ajustar cortes, áudio, títulos, legendas e transições; salvar; produzir prévia; inspecionar; exportar; verificar arquivos e avisos.

**Saída:** projeto `.fcproj`, `assembly_plan.json`, `editing_bundle.json`, log de operações, snapshots observáveis do projeto, prévia e `master.mp4`.

**Critério para avançar:** projeto salvo, dependências resolvidas, nenhuma mídia offline, exportação concluída e arquivo inspecionável. Resultado de exportação bem-sucedido com placeholders de mídia offline é falha para entrega final.

**Memória:** parâmetros efetivamente aceitos, falhas de comandos, alterações observadas no projeto e resultado técnico. Não atribuir ao usuário uma decisão estética que só foi inferida pelo agente.

### Estágio 6 — Revisão, correções e pacote final

**Entrada:** todas as entregas, arquivo final, perfil e critérios de revisão.

**Processamento:** verificar conteúdo/fontes, direitos, correspondência visual, voz, sincronização, duração, resolução e áudio; gerar título, thumbnail, descrição, capítulos, legendas e créditos; encaminhar correções ao estágio responsável. Reutilizar QC e empacotamento existentes.

**Saída:** `review_bundle.json`, relatórios técnicos/editoriais, pacote autocontido e pendências de publicação.

**Critério para encerrar:** verificações obrigatórias aprovadas, nenhuma falha essencial omitida e pacote íntegro. Correção automática tem orçamento de tentativas; esgotamento encerra com diagnóstico, não com repetição ilimitada ou relaxamento de critérios.

**Memória:** resultados medidos, avaliações do usuário e, futuramente, métricas importadas de audiência. Não inventar retenção, custo ou aprovação quando não houver dados.

## 6. Perfis e memória autônoma

### 6.1 Escopos

1. **Base técnica:** conhecimento explicitamente classificado como independente de canal, como incompatibilidade de codec em uma versão de ferramenta.
2. **Modelo de nicho:** conjunto opcional de configurações iniciais e referências. Copiado para o canal ao criar o perfil; mudanças no modelo não se propagam silenciosamente.
3. **Canal:** identidade, configurações explícitas, aprendizados ativos, hipóteses, exemplos e histórico próprios.
4. **Episódio:** exceções, decisões e configurações da produção em andamento.

Precedência: instrução explícita do episódio -> instrução explícita do canal -> aprendizado aplicável do canal -> padrão herdado. Regras de integridade e direitos continuam obrigatórias; a precedência editorial não desliga esses requisitos.

### 6.2 Persistência

Banco local em `data/profiles/profiles.sqlite3`, com migrações versionadas, transações, chaves estrangeiras e índices de escopo. Mídia e conteúdo extenso permanecem em arquivos referenciados por hash; não inserir áudio/vídeo no banco.

Tabelas propostas: `profiles`, `profile_revisions`, `productions`, `observations`, `learning_candidates`, `learning_evaluations`, `learning_revisions` e `memory_events`. O RunStore não é substituído por outra tabela de tentativas; produções e observações referenciam seus manifests.

Toda leitura de memória exige escopo explícito. Acesso a observação de outro perfil resulta em erro de escopo ou ausência, nunca em conteúdo do outro canal. Referências de produção também validam pertencimento ao perfil. A base técnica tem escopo próprio, acessado por operação distinta; não usar `profile_id=None` para significar acesso irrestrito.

Adotar transações curtas, conexão por operação/worker e tratamento de concorrência. Não manter uma transação aberta enquanto um LLM ou editor trabalha. Usar revisão esperada na ativação para detectar alterações concorrentes.

### 6.3 Observação versus aprendizado

`Observation` registra `observation_id`, `profile_id`, `production_id`, estágio, tentativa, tipo, origem, horário, resumo, referências de evidência, configuração efetiva, versões de ferramentas e `event_key` idempotente.

`LearningCandidate` registra escopo, estágio aplicável, condição de aplicação, mudança proposta, IDs de evidência, avaliador necessário e estado. Sua ação deve ser um patch tipado de configuração ou um procedimento conhecido; texto livre de um modelo não pode executar comandos arbitrários.

`LearningEvaluation` registra candidato, versão, ensaio/comparação realizado, evidências, verificações aplicáveis, resultado e justificativa. Um valor de confiança pode ser informado, mas não substitui evidência e não será calibrado agora.

`LearningRevision` guarda ação ativa, condição de aplicação, versões compatíveis de ferramentas/modelos, evidências, data e referência da versão substituída. Não apaga a observação original.

### 6.4 Ciclo automático

```text
observed -> proposed -> evaluating -> active
                         |            |
                         v            v
                      rejected     suspended -> evaluating
                                      |
                                      v
                                  superseded
```

`observed` pertence à observação; `proposed`, `evaluating`, `active`, `rejected`, `suspended` e `superseded` pertencem ao candidato/aprendizado. Não usar esse ciclo como substituto dos estados de execução.

O agente revisor agrupa observações por contexto, formula uma proposta estruturada, escolhe um avaliador e executa uma amostra ou checagem adequada. Pode ativar a proposta sem confirmação humana se os requisitos da política forem atendidos. Se faltar critério mensurável, dados ou uma ferramenta capaz de verificar, a proposta permanece hipótese com motivo registrado.

A aprendizagem ocorre ao terminar estágios, na revisão final e após feedback ou importação de um projeto editado. Não criar daemon ou agendamento periódico nesta atualização. Mudança de ferramenta/modelo exige verificar compatibilidade dos aprendizados afetados.

### 6.5 Aplicação, suspensão e reversão

- Fixar um snapshot do perfil ao iniciar cada produção. Atualizações automáticas valem para próximas produções.
- Correção do episódio atual cria um plano explícito de retrabalho, mantendo a linhagem do snapshot original e os overrides da correção.
- Ativação gera nova revisão; suspensão restaura a configuração anterior aplicável e preserva o motivo.
- Uma falha de verificação relacionada ao ajuste pode disparar suspensão automática. Não atribuir toda queda de audiência ao último ajuste.
- Logs distinguem intenção, comando enviado e estado realmente observado. Comando enviado não comprova mudança aceita.
- Alterações manuais são capturadas por comparação de snapshots observáveis do FilmCraft; mudanças transitórias entre snapshots não podem ser reconstruídas com certeza.
- O resumo entregue ao agente inclui somente contexto relevante e referências; o histórico completo continua consultável.
- Prompts, respostas e fontes podem ser arquivados com redação de segredos. Conteúdo externo é evidência, nunca autoridade para alterar políticas de execução.

### 6.6 Fora da calibração inicial

Não definir nesta fase números universais de tentativas, fontes, duração de plano, velocidade, volume de música, pesos de relevância ou confiança. As políticas terão campos validados e valores explícitos no perfil/piloto quando forem escolhidos. Sem orçamento de operação configurado, preflight impede iniciar etapas externas potencialmente ilimitadas; não inventar um limite silencioso.

Operações declaradas pelo usuário como preferências são registradas diretamente como configuração explícita. Preferências deduzidas de métricas ou de mudanças manuais continuam sujeitas a avaliação automática, sem uma aprovação humana obrigatória.

## 7. Integração com FilmCraft

### Evidência e limites conhecidos

O projeto documenta MCP nativo com modo headless e modo bridge para o aplicativo aberto, importação de mídia, inspeção, execução em lote, prévias e exportação. O guia também informa que uma exportação pode concluir com mídia offline e que o uso de codificador por hardware pode recair para software. O adaptador deve verificar os resultados, não apenas a ausência de erro.

Fontes oficiais verificadas para este plano:

- [Repositório e estado alpha](https://github.com/storytold/filmcraft).
- [Agentes e ferramentas MCP](https://github.com/storytold/filmcraft/blob/main/docs/agents.md).
- [Canal de controle e MCP](https://github.com/storytold/filmcraft/blob/main/docs/control-protocol.md).

### Estratégia

- Começar em bridge para permitir revisão no aplicativo; encapsular transporte para suportar headless futuramente.
- Usar o servidor MCP que acompanha FilmCraft. Criar um cliente/adaptador no AI Video Factory, não um editor novo nem um servidor intermediário desnecessário.
- Obter catálogo e parâmetros reais na conexão. Versionar o mapa de capacidades; não assumir que o exemplo do README é o contrato completo da versão instalada.
- Priorizar comandos estruturados; ações de mouse/teclado são exceções explícitas, não o caminho padrão.
- Mapear tempo do plano para o timebase documentado pelo editor: 254.016.000.000 ticks por segundo, confirmando a versão/capacidade. Converter a partir de quadros/amostras usando aritmética racional; evitar acumulação de floats.
- Não somar duração de transição ao tempo da fala indevidamente. O plano deve distinguir sobreposição, intervalo de origem e tempo na sequência.
- Persistir mapa `scene_id/shot_id -> item/clip` e checkpoints de montagem. Após queda ou timeout de mutação, inspecionar antes de repetir.
- Lotes MCP não são presumidos transacionais. Registrar os passos confirmados; reconciliar um lote parcialmente aplicado.
- Manter narração, música, imagens/vídeos e textos em faixas distinguíveis. Não exigir recursos ainda não confirmados no catálogo instalado.
- Salvar projeto e manifesto de mídias antes de exportar; validar todos os arquivos referenciados, avisos, mídia offline, arquivo final e encoder efetivamente usado.
- Segredo do bridge é herdado do ambiente. Não copiá-lo para perfil, SQLite, prompts ou logs.

FilmCraft desloca a responsabilidade de montagem/exportação para o editor. Não presumir economia de CPU/GPU, nem renderização remota, por usar MCP. Medir no piloto.

## 8. Interfaces propostas

Interfaces abaixo são novas e devem ser implementadas com estes nomes. Funções existentes citadas nas tarefas permanecem adaptadas em suas fronteiras atuais. Tipos de domínio desta seção vivem em `workflow/models.py` ou `profiles/models.py` conforme a tabela de arquivos.

```python
StageName = Literal["research", "script", "narration", "media", "editing", "review"]

class StageRunner(Protocol):
    def run(self, context: StageContext, inputs: StageInputs) -> StageResult: ...

class TtsProvider(Protocol):
    def capabilities(self) -> TtsCapabilities: ...
    def synthesize(self, request: SpeechRequest, destination: Path) -> SpeechResult: ...

class FilmCraftClient(Protocol):
    def connect(self) -> EditorCapabilities: ...
    def inspect(self) -> EditorSnapshot: ...
    def execute(self, command_id: str, params: dict[str, Any]) -> EditorCommandResult: ...
    def close(self) -> None: ...

class CandidateEvaluator(Protocol):
    def evaluate(self, candidate: LearningCandidate, context: StageContext) -> LearningEvaluation: ...
```

- `StageInputs`: mapa de `StageName` para referências de bundles concluídos, carregados e validados pelo runner; só contém predecessores necessários.
- `TtsCapabilities`: idiomas, vozes e recursos de pausa/alinhamento realmente suportados; `SpeechRequest`: texto canônico, texto falável, idioma, voz, instruções e IDs de cena/segmento; `SpeechResult`: artefato, provedor/modelo/voz efetivos, metadados e duração.
- `EditorCapabilities`: versão, catálogo de comandos e capacidades confirmadas; `EditorSnapshot`: estado estruturado de projeto/sequência e referências; `EditorCommandResult`: resultado tipado, avisos, status de job e erros. Respostas brutas redigidas ficam como evidência auxiliar.
- `MemoryContext`: regras aplicáveis, configurações resolvidas, exemplos e referências, com digest e escopo.
- `ProductionResult`: ID, estado, estágio final alcançado, artefatos/pacote, falhas e IDs de revisões de memória criadas.

```python
# profiles/store.py — métodos de ProfileStore
create_profile(spec: ProfileSpec) -> ProfileSnapshot
get_snapshot(profile_id: str, revision: int | None = None) -> ProfileSnapshot
revise_profile(profile_id: str, patch: ProfilePatch, *, expected_revision: int, reason: str) -> ProfileSnapshot
record_observation(observation: Observation) -> str
list_observations(profile_id: str, *, stage: StageName | None = None) -> list[Observation]
list_learnings(profile_id: str, *, stage: StageName | None = None) -> list[LearningRevision]
save_candidate(candidate: LearningCandidate) -> str
save_evaluation(evaluation: LearningEvaluation) -> str
activate_learning(candidate_id: str, evaluation_id: str, *, expected_revision: int) -> ProfileSnapshot
suspend_learning(profile_id: str, learning_id: str, *, expected_revision: int, reason: str) -> ProfileSnapshot

# profiles/context.py
build_memory_context(store: ProfileStore, snapshot: ProfileSnapshot, stage: StageName, topic: str) -> MemoryContext
stage_settings_digest(snapshot: ProfileSnapshot, stage: StageName) -> str

# profiles/learning.py
review_observations(context: StageContext, observations: list[Observation], reviewer: LearningReviewer) -> list[LearningCandidate]
evaluate_and_apply(context: StageContext, candidate: LearningCandidate, evaluator: CandidateEvaluator, store: ProfileStore) -> LearningEvaluation

# workflow/orchestrator.py
run_production(request: ProductionRequest, *, store: ProfileStore, runners: Mapping[StageName, StageRunner], through: StageName = "review", resume: bool = True, dry_run: bool = False) -> ProductionResult
plan_invalidation(changed_inputs: set[str]) -> list[StageName]

# workflow/planning.py
build_assembly(script: ScriptBundle, narration: NarrationBundle, media: MediaBundle, snapshot: ProfileSnapshot) -> AssemblyPlan
```

`LearningReviewer` é `Callable[[StageContext, list[Observation]], list[LearningCandidate]]`, com implementação baseada no adaptador LLM existente e transporte injetável nos testes. `ProfileSpec` define identidade e configurações iniciais; `ProfilePatch` restringe alterações tipadas; `Observation` e modelos de aprendizagem seguem a seção 6. `ReviewPolicy`, `LearningPolicy` e `OperationBudget` são submodelos do perfil, sem pesos finos fixados por este plano.

## 9. Mapa de arquivos

Criar os `__init__.py` necessários nos novos pacotes. Não mover os módulos legados sem necessidade para estas entregas.

| Criar | Responsabilidade |
|---|---|
| `src/ai_video_factory/platform_support.py` | Lock de arquivo multiplataforma, caminhos de executáveis e fontes |
| `src/ai_video_factory/workflow/models.py` | Contratos de produção, bundles, plano de montagem e resultados |
| `src/ai_video_factory/workflow/contracts.py` | Protocolos de runners/provedores/editor/avaliador |
| `src/ai_video_factory/workflow/orchestrator.py` | Sequência, retomada, invalidação, correções e observações |
| `src/ai_video_factory/workflow/planning.py` | Montagem baseada em áudio e planos, independente do editor |
| `src/ai_video_factory/profiles/models.py` | Perfil, políticas, snapshots, observações e aprendizados |
| `src/ai_video_factory/profiles/store.py` | SQLite, migrações, consultas com escopo e revisões |
| `src/ai_video_factory/profiles/context.py` | Resolução de precedência e resumo por estágio |
| `src/ai_video_factory/profiles/learning.py` | Revisão automática, avaliação e ativação/suspensão |
| `src/ai_video_factory/stages/research.py` | Estágio 1 e descoberta de fontes no tema |
| `src/ai_video_factory/stages/script.py` | Estágio 2, vínculo com evidências e direção |
| `src/ai_video_factory/stages/narration.py` | Estágio 3, síntese e medição por segmento |
| `src/ai_video_factory/stages/media.py` | Estágio 4, seleção por plano e direitos |
| `src/ai_video_factory/stages/editing.py` | Estágio 5 e reconciliação da montagem |
| `src/ai_video_factory/stages/review.py` | Estágio 6, correções e pacote |
| `src/ai_video_factory/integrations/tts.py` | Adaptador para TTS atual e fronteira para outros softwares |
| `src/ai_video_factory/integrations/filmcraft.py` | Cliente MCP, capabilities e tradução de montagem |
| `src/ai_video_factory/profile_cli.py` | Comandos de perfil, memória, feedback e exportação |
| `src/ai_video_factory/workflow_cli.py` | Comandos do fluxo de seis estágios |
| `config/filmcraft.example.toml` | Exemplo sem segredos de caminho/modo/conexão |
| `config/profile.example.json` | Perfil ilustrativo, sem declarar nicho/idioma como decisão do usuário |
| `docs/profile-memory.md` e `docs/filmcraft-setup.md` | Operação e recuperação, criados durante a implementação |

Modificar conforme as tarefas: `cli.py`, `run_store.py`, `scheduler.py`, `video_pipeline.py`, `daily_job.py`, `production.py`, `narration.py`, `asset_memory.py`, `preflight.py`, `doctor.py`, `publisher.py`, `pyproject.toml`, `uv.lock`, `.gitignore`, README e testes. Mudanças em `longform.py`, `script_generator.py`, `subtitle_export.py` e provedores devem ser incrementais.

## 10. Sequência de implementação

Cada tarefa segue o ciclo: teste de comportamento que falha -> implementação mínima -> testes pertinentes passando -> commit focado. Os comandos abaixo são para execução futura, não foram executados ao escrever este plano. Não criar testes que apenas espelhem detalhes internos.

### Tarefa 1 — Linha de base e execução no Windows

**Arquivos:** criar `platform_support.py` e `tests/test_platform_support.py`; modificar `video_pipeline.py`, `scheduler.py`, `narration.py`, `preflight.py`, `thumbnail.py` e `doctor.py` apenas nas fronteiras de plataforma.

**Interfaces:** produzir `exclusive_file_lock(path: Path) -> ContextManager[None]`, `resolve_venv_executable(venv: Path, name: str) -> Path` e `resolve_font() -> Path | None`; consumidores deixam de importar `fcntl` diretamente.

- [ ] Registrar revisão, ferramentas disponíveis e resultado da coleta de testes. Executar `python -m pytest --collect-only -q` no ambiente do projeto; se faltarem dependências, registrar o bloqueio e preparar o ambiente na execução.
- [ ] Criar teste de dois processos competindo pelo mesmo lock e liberação após erro; testar executável em `Scripts` no Windows e `bin` no Linux, caminhos com espaços e fonte indisponível.
- [ ] Executar `python -m pytest tests/test_platform_support.py -q`; confirmar falha antes de implementar.
- [ ] Implementar lock com bibliotecas padrão de cada plataforma ou dependência pequena justificada; imports específicos devem ser condicionais.
- [ ] Executar os novos testes e `python -m ai_video_factory.cli --help`; o CLI deve importar no Windows sem `fcntl`.
- [ ] Registrar baseline e commit `fix: support native Windows execution boundaries`.

**Entrega:** ambiente importável e limites de plataforma explícitos, sem instalar modelos ou alterar GPU.

### Tarefa 2 — Contratos de estágio, perfil e montagem

**Arquivos:** criar `workflow/models.py`, `workflow/contracts.py`, `profiles/models.py`, seus pacotes e `tests/test_workflow_models.py`.

**Interfaces:** produzir todos os tipos definidos nas seções 4, 6 e 8. `StageInputs` deve transportar referências tipadas e validar a versão dos bundles ao carregar.

- [ ] Escrever testes de serialização/releitura dos seis bundles; IDs de cena/plano duplicados, durações inválidas e referência a cena inexistente devem falhar.
- [ ] Definir testes nomeados `test_script_roundtrip_preserves_direction_and_evidence` e `test_invalid_scene_reference_is_rejected`, com asserções sobre todos os campos editoriais e a exceção de validação.
- [ ] Testar que um roteiro mantém fala, pausa, direção, fontes e múltiplos planos depois de salvar e carregar.
- [ ] Executar `python -m pytest tests/test_workflow_models.py -q` e confirmar falha inicial.
- [ ] Implementar modelos e validações cruzadas. `EditDocument` legado permanece inalterado; conversões são explícitas.
- [ ] Reexecutar testes novos e `tests/test_edit_schema.py`; exigir aprovação dos formatos antigos e novos.
- [ ] Commit `feat: define staged production and profile contracts`.

**Entrega:** contratos suficientes para implementar os estágios independentemente.

### Tarefa 3 — Perfis versionados em SQLite

**Arquivos:** criar `profiles/store.py` e `tests/test_profile_store.py`; modificar `.gitignore` para excluir o banco e os arquivos SQLite auxiliares.

**Interfaces:** implementar criação, leitura e revisão de perfil da seção 8; caminhos de armazenamento recebidos pelo construtor, sem depender do diretório de trabalho.

- [ ] Testar criação de dois perfis, leitura após reabrir o banco, revisão anterior imutável e conflito de revisão concorrente.
- [ ] Testar migração repetida sem perda, transação interrompida e referência a produção de outro perfil rejeitada.
- [ ] Executar `python -m pytest tests/test_profile_store.py -q`; confirmar falha inicial.
- [ ] Implementar migração inicial, constraints e transações. Exportar configurações sem segredos.
- [ ] Reexecutar os testes; confirmar que escrever revisão 2 não altera snapshot da revisão 1.
- [ ] Commit `feat: persist isolated versioned channel profiles`.

**Entrega:** identidade e configurações persistentes por canal, com reversão possível.

### Tarefa 4 — Observações, candidatos e evidências por perfil

**Arquivos:** estender `profiles/store.py`; criar `tests/test_profile_observations.py`; adaptar `asset_memory.py` por fronteira explícita de escopo.

**Interfaces:** produzir `record_observation`, `list_observations`, `save_candidate`, `save_evaluation` e `list_learnings` da seção 8.

- [ ] Testar evento repetido com mesmo `event_key`: apenas uma observação; tentativa nova deve gerar outro evento.
- [ ] Testar rejeição editorial no perfil A e uso permitido no B; registro técnico compartilhado exige classificação explícita.
- [ ] Executar `python -m pytest tests/test_profile_observations.py tests/test_asset_memory.py -q`; confirmar o comportamento novo ausente antes da implementação.
- [ ] Implementar escopo obrigatório, evidências referenciadas e importação do legado como histórico técnico não promovido automaticamente.
- [ ] Confirmar por testes que consultas de A não retornam dados de B e que os dados legados não viram preferências editoriais.
- [ ] Commit `feat: record scoped production evidence and learning candidates`.

**Entrega:** histórico auditável sem contaminação entre canais.

### Tarefa 5 — Contexto relevante e configurações efetivas

**Arquivos:** criar `profiles/context.py` e `tests/test_memory_context.py`.

**Interfaces:** implementar `build_memory_context` e `stage_settings_digest`; consumir snapshots, aprendizagens e regras de precedência.

- [ ] Testar preferência explícita vencendo inferência, exceção do episódio, regra incompatível com versão de ferramenta e resumo filtrado por estágio.
- [ ] Testar que mudar somente uma configuração de edição não muda o digest de pesquisa; mudar fonte preferida muda o digest de pesquisa.
- [ ] Fixar os testes `test_editing_change_preserves_research_digest` e `test_old_snapshot_resolves_superseded_learning`; o segundo compara o contexto anterior depois da ativação de uma regra nova.
- [ ] Executar `python -m pytest tests/test_memory_context.py -q`; confirmar falha inicial.
- [ ] Implementar resolução determinística e seleção com referências. Não montar o contexto concatenando todo o histórico.
- [ ] Verificar snapshot fixado: nova revisão do perfil não muda contexto de uma produção já iniciada.
- [ ] Commit `feat: resolve stage-specific memory and effective settings`.

**Entrega:** contexto reproduzível e limitado ao que cada agente precisa.

### Tarefa 6 — Coordenador e retomada dos seis estágios

**Arquivos:** criar `workflow/orchestrator.py`, `tests/test_staged_workflow.py` e fixtures locais necessárias; estender `run_store.py` somente se a integração exigir.

**Interfaces:** implementar `run_production` e `plan_invalidation`; consumir `StageRunner.run` e `StageResult`.

- [ ] Criar runners determinísticos de teste; testar ordem, parada em `through`, falha impedindo sucessores e retomada com predecessores válidos.
- [ ] Testar `plan_invalidation({"editing.music"}) == ["editing", "review"]` e alterações de fala invalidando narração e dependentes.
- [ ] Nomear esse contrato como `test_music_change_invalidates_only_editing_and_review`, com a asserção literal `assert plan_invalidation({"editing.music"}) == ["editing", "review"]`.
- [ ] Executar `python -m pytest tests/test_staged_workflow.py -q`; confirmar falha inicial.
- [ ] Persistir pedido/snapshot antes de chamar serviços; incluir digests das entradas, ferramentas e regras relevantes nos fingerprints.
- [ ] Registrar resultado e observações com chave idempotente. Se houver queda entre RunStore e SQLite, reconciliar no próximo início usando o resultado persistido.
- [ ] Executar testes novos e `tests/test_run_store.py`; `dry_run` não chama LLM/TTS/MCP/rede e não ativa aprendizados.
- [ ] Commit `feat: orchestrate resumable six-stage productions`.

**Entrega:** fluxo navegável com runners de teste e reaproveitamento correto de entregas.

### Tarefa 7 — Pesquisa aprofundada a partir do tema

**Arquivos:** criar `stages/research.py` e `tests/test_stage_research.py`; adaptar `research_pipeline.py`, `research.py` e configuração de provedores apenas no necessário.

**Interfaces:** produzir `ResearchStage.run`; consumir `ProductionRequest`, `MemoryContext` e `run_research(...)` existente; entregar `ResearchBundle`.

- [ ] Testar tema explícito preservado apesar de uma tendência alheia; descoberta com consultas temáticas; fontes iniciais opcionais.
- [ ] Testar evidência extraída de conteúdo real, divergência mantida como divergência e ausência de conteúdo impedindo alegação de verificação.
- [ ] Executar `python -m pytest tests/test_stage_research.py -q`; confirmar falha inicial.
- [ ] Implementar descoberta e expansão limitadas por `OperationBudget`, persistindo conteúdo e reutilizando o modo de produção de pesquisa.
- [ ] Registrar falhas temporárias e relevância contextual como observações distintas; criar síntese e bundle.
- [ ] Executar testes novos e regressões de pesquisa/proveniência; commit `feat: research supplied topics with traceable evidence`.

**Entrega:** dossiê real que alimenta o roteiro, sem substituição silenciosa do tema.

### Tarefa 8 — Roteiro completo de fala e direção

**Arquivos:** criar `stages/script.py` e `tests/test_stage_script.py`; adaptar `longform.py`, `formats.py` e `script_generator.py` para reutilização sem perder campos.

**Interfaces:** produzir `ScriptStage.run`, entregando `ScriptBundle`; consumir `ResearchBundle` e perfil.

- [ ] Testar que cada afirmação factual aponta para evidência existente; referência inventada falha; incerteza permanece atribuída.
- [ ] Testar round-trip de cena com fala, pausas, intenção, texto, planos e transições; idioma vem do perfil.
- [ ] Executar `python -m pytest tests/test_stage_script.py -q`; confirmar falha inicial.
- [ ] Implementar geração por capítulos/partes, validação e revisão estruturada dentro do orçamento; produzir Markdown legível a partir do JSON validado.
- [ ] Verificar que roteiro insuficiente é revisado ou falha, sem repetição artificial para completar tempo.
- [ ] Executar testes novos e regressões de longform; commit `feat: generate source-linked narration and visual direction`.

**Entrega:** roteiro que outro agente pode executar sem reconstruir a intenção editorial.

### Tarefa 9 — TTS separado e tempo real da narração

**Arquivos:** criar `integrations/tts.py`, `stages/narration.py` e `tests/test_stage_narration.py`; adaptar `narration.py` e integrar `whisper_timing.py` opcionalmente.

**Interfaces:** produzir `TtsProvider`, `TtsCapabilities`, `SpeechRequest`, `SpeechResult` e `NarrationStage.run`; `NarrationBundle` aponta para arquivos por segmento.

- [ ] Testar provedor sem suporte ao idioma: falha de capacidade, sem fallback oculto; voz efetiva diferente deve aparecer no resultado.
- [ ] Testar texto narrado mantendo conteúdo, pausa representada explicitamente, duração medida e metadado de alinhamento exato/aproximado.
- [ ] Executar `python -m pytest tests/test_stage_narration.py -q`; confirmar falha inicial.
- [ ] Implementar adaptador do TTS existente e fronteira para outro software; não escolher fornecedor pago sem necessidade definida.
- [ ] Usar WAV real de fixture para medição; voz sintética de teste não conta como piloto de qualidade. Não misturar música nesta etapa.
- [ ] Executar testes novos e de legendas/alinhamento afetados; commit `feat: separate narration providers and measured segment timing`.

**Entrega:** áudio modular rastreável no idioma do perfil, base temporal da montagem.

### Tarefa 10 — Mídia por plano e direitos

**Arquivos:** criar `stages/media.py` e `tests/test_stage_media.py`; adaptar `stock_providers.py`, `stock_media.py`, `assets.py`, `asset_qc.py` e `asset_memory.py`.

**Interfaces:** produzir `MediaStage.run` e `MediaBundle`; consumir roteiro e narração medidos; entregar múltiplos planos por cena.

- [ ] Testar uma cena longa com vários planos, arquivo próprio, candidato irrelevante, duplicação e ausência de mídia.
- [ ] Testar licença ausente bloqueando final; licença permitida e atribuição preservadas; rejeição contextual isolada por perfil.
- [ ] Executar `python -m pytest tests/test_stage_media.py -q`; confirmar falha inicial.
- [ ] Implementar busca, seleção, recorte e cache com direitos preservados; distinguir qualidade técnica de correspondência semântica.
- [ ] Registrar lacunas e alternativas de composição; geração por IA permanece opcional e não representa evidência de evento real.
- [ ] Executar testes novos e de assets/stock afetados; commit `feat: acquire licensed scene-matched shots with scoped memory`.

**Entrega:** pacote visual executável com correspondência e direitos rastreáveis.

### Tarefa 11 — Cliente MCP do FilmCraft e diagnóstico

**Arquivos:** criar `integrations/filmcraft.py`, `config/filmcraft.example.toml`, `tests/test_filmcraft_client.py` e `docs/filmcraft-setup.md`; adaptar `preflight.py`, `doctor.py`, `pyproject.toml` e `uv.lock`.

**Interfaces:** implementar `FilmCraftMcpClient` aderente a `FilmCraftClient`; produzir capabilities e resultados tipados da seção 8.

- [ ] Confirmar documentação da versão instalada e cliente MCP oficial antes de escolher/pinar a dependência opcional no extra `filmcraft`.
- [ ] Testar negociação, catálogo, comando indisponível, erro estruturado, timeout, reconexão e encerramento de sessão com transporte de teste.
- [ ] Testar que timeout de mutação retorna estado indeterminado e exige inspeção, sem repetição automática cega.
- [ ] Executar `python -m pytest tests/test_filmcraft_client.py -q`; confirmar falha inicial.
- [ ] Implementar cliente MCP stdio/bridge conforme documentação; segredos herdados e redigidos. A ausência do extra não impede usar o CLI legado.
- [ ] Acrescentar diagnóstico de executáveis, bridge e capacidades, sem iniciar editor ou exportar durante inspeção read-only.
- [ ] Executar testes novos e de preflight; commit `feat: connect FilmCraft through its native MCP server`.

**Entrega:** conexão diagnosticável com o editor; nenhum ganho de desempenho presumido.

### Tarefa 12 — Plano de montagem, edição e reconciliação

**Arquivos:** criar `workflow/planning.py`, `stages/editing.py`, `tests/test_assembly_plan.py` e `tests/test_stage_editing.py`.

**Interfaces:** implementar `build_assembly` e `EditingStage.run`; consumir os bundles e `FilmCraftClient`; produzir `EditingBundle`.

- [ ] Testar tempos reais da voz, múltiplos planos, pausas, transição com sobreposição e conversão racional para ticks sem drift acumulado.
- [ ] Testar resolução final 1920×1080, salvamento do projeto e ausência de pós-processamento legado de recorte.
- [ ] Testar queda após inserir clipe mas antes de salvar o log local: retomar inspecionando e reaproveitando o item, sem duplicação.
- [ ] Testar lote parcialmente aplicado e projeto manualmente alterado; detectar divergência antes de sobrescrever.
- [ ] Fixar `test_resume_after_applied_command_does_not_duplicate_clip`: após queda simulada e retomada, a inspeção contém exatamente um item para o mesmo `shot_id` e nenhuma segunda chamada de inserção.
- [ ] Executar `python -m pytest tests/test_assembly_plan.py tests/test_stage_editing.py -q`; confirmar falha inicial.
- [ ] Implementar plano independente do editor, tradução por catálogo e checkpoints. Prever pontos de captura antes/depois de correções manuais, sem alegar observação contínua.
- [ ] Confirmar exportação concluída, encoder efetivo, avisos e ausência de mídia offline; validar arquivo com ffprobe.
- [ ] Reexecutar testes e commit `feat: assemble and reconcile FilmCraft projects from staged artifacts`.

**Entrega:** montagem inspecionável e retomável, com projeto editável e master real.

### Tarefa 13 — Revisão final, retrabalho e pacote

**Arquivos:** criar `stages/review.py` e `tests/test_stage_review.py`; adaptar `qc_final.py`, `qc_editorial.py`, `publisher.py`, `packaging.py` e `subtitle_export.py` quando necessário.

**Interfaces:** produzir `ReviewStage.run` e `ReviewBundle`; consumir bundles completos e arquivo medido; reutilizar `build_package(...)` existente.

- [ ] Testar exportação tecnicamente válida com mídia offline: reprovar; testar duração divergente, referência factual quebrada e créditos ausentes.
- [ ] Testar encaminhamento de erro de pronúncia ao estágio 3 e invalidação dos dependentes, preservando a pesquisa.
- [ ] Executar `python -m pytest tests/test_stage_review.py -q`; confirmar falha inicial.
- [ ] Implementar relatório de métricas reais, decisões editoriais separadas e correções limitadas por orçamento; sem relaxar checks para aprovar.
- [ ] Montar pacote com master, projeto/manifesto de dependências, thumbnail, títulos, descrição, fontes, créditos, capítulos e legendas.
- [ ] Testar que este caminho nunca chama upload/publicação e que o estado de aprovação existente permanece separado do aprendizado autônomo.
- [ ] Reexecutar regressões afetadas e commit `feat: review staged productions and package verified outputs`.

**Entrega:** pacote revisável e falhas encaminhadas à origem correta.

### Tarefa 14 — Aprendizagem autônoma e reversão

**Arquivos:** criar `profiles/learning.py` e `tests/test_profile_learning.py`; integrar hooks no coordenador e nos runners.

**Interfaces:** implementar `review_observations`, `evaluate_and_apply`, `activate_learning` e `suspend_learning`; consumir avaliadores injetáveis e políticas tipadas.

- [ ] Testar sequência observação -> proposta -> avaliação -> ativação sem aprovação humana; candidato sem evidência permanece hipótese.
- [ ] Fixar `test_verified_learning_activates_without_human_approval` e `test_unsupported_learning_stays_proposed`, verificando revisão incrementada apenas no primeiro e nenhuma solicitação de aprovação em ambos.
- [ ] Testar patch fora do escopo, tentativa de alterar preferência explícita e instrução em fonte externa: nenhuma altera configuração operacional.
- [ ] Testar falha relacionada ao ajuste suspendendo a regra e recuperando revisão anterior; nova versão do editor suspende regra incompatível.
- [ ] Testar que produção em andamento mantém seu snapshot e a próxima adota o aprendizado ativo.
- [ ] Testar comparação de estado manual do editor como observação, sem inferir intenção confirmada; feedback explícito do usuário permanece distinguível.
- [ ] Executar `python -m pytest tests/test_profile_learning.py -q`; confirmar falha inicial.
- [ ] Implementar revisor com LLM por transporte injetável, verificação tipada de ações e avaliadores de correção técnica. Avaliações editoriais incertas permanecem hipóteses; incluir ensaios controlados sem alterar pesos finos neste marco.
- [ ] Impedir loops ilimitados: cada avaliação consome orçamento do perfil e registra motivo quando adiada.
- [ ] Reexecutar testes do coordenador e memória; commit `feat: apply evidence-backed channel learning autonomously`.

**Entrega:** memória ativa que muda próximas produções sozinha, com rastreabilidade e reversão.

### Tarefa 15 — CLI de perfis, produção e memória

**Arquivos:** criar `profile_cli.py`, `workflow_cli.py`, `config/profile.example.json`, `tests/test_profile_cli.py` e `tests/test_workflow_cli.py`; modificar `cli.py`, `scheduler.py`, `daily_job.py` e README nas fronteiras necessárias.

**Interfaces:** grupos novos `profiles` e `workflow`; comandos legados preservados. Produção nova sempre exige perfil explícito; nunca inferir canal de uma variável global.

- [ ] Testar criar/listar/mostrar perfil; iniciar produção até um estágio; retomar; listar aprendizados; registrar feedback; exportar perfil e memória.
- [ ] Testar escolha explícita do perfil, erro de configuração claro e `dry-run` sem chamadas externas ou ativação de regras.
- [ ] Executar `python -m pytest tests/test_profile_cli.py tests/test_workflow_cli.py -q`; confirmar falha inicial.
- [ ] Implementar comandos e importação explícita de `channels.toml`. Templates fornecem ponto de partida, sem inventar idioma/nicho do usuário.
- [ ] Integrar scheduler/daily ao coordenador apenas quando configurados para o fluxo novo; preservar deduplicação e fila atuais. Não habilitar agendamento ou upload automaticamente.
- [ ] Reexecutar `tests/test_cli.py`, regressões de scheduler/daily afetadas e testes novos.
- [ ] Commit `feat: expose staged workflows and autonomous profile memory in CLI`.

**Entrega:** caminho utilizável do início ao pacote, com inspeção da memória.

### Tarefa 16 — Migração, integração e piloto real

**Arquivos:** criar `tests/test_profile_workflow_integration.py`, `tests/test_profile_migration.py`, `docs/profile-memory.md`; atualizar `docs/filmcraft-setup.md`, README e documentação de compatibilidade.

**Interfaces:** consumir todos os contratos anteriores; nenhuma nova coordenação paralela.

- [ ] Testar dois perfis completos com transporte determinístico, mesmo arquivo de mídia e aprendizados diferentes; não vazar configuração, regra ou artefato entre canais.
- [ ] Testar importação idempotente de configurações e memória legadas; runs sem perfil ficam no legado, sem atribuição inventada a um canal.
- [ ] Testar backup/restauração de SQLite e referências de artefatos, migração de schema e retomada após interrupção.
- [ ] Executar testes novos; corrigir a implementação até passarem, sem alterar evidências de aceitação.
- [ ] Executar suíte Python completa e verificações Remotion pertinentes se caminhos compartilhados mudarem; registrar comandos e resultados reais.
- [ ] Com tema, idioma, ferramentas e orçamento configurados, produzir amostra curta com fontes, voz e mídia reais; conferir projeto no FilmCraft e arquivo final.
- [ ] Produzir um episódio completo de 20–30 minutos e testar retomada de uma etapa interrompida. Registrar custo quando conhecido, tempo, recursos e correções; desconhecido deve aparecer como desconhecido.
- [ ] Repetir em mais dois episódios do mesmo perfil para avaliar consistência. Testes determinísticos demonstram isolamento; três vídeos não demonstram causalidade de desempenho editorial.
- [ ] Encerrar com relatório de piloto e limitações observadas; commit `docs: document staged production migration and pilot results`.

**Entrega:** integração comprovada no ambiente-alvo, com operação e recuperação documentadas.

## 11. Marcos e dependências

| Marco | Tarefas | Evidência para encerrar |
|---|---|---|
| M0 — Base executável | 1 | CLI importável no Windows e baseline registrado |
| M1 — Perfil e contratos | 2–5 | Isolamento, versões, observações e contexto testados |
| M2 — Coordenação | 6 | Ordem, retomada e invalidação passando com runners determinísticos |
| M3 — Conteúdo e materiais | 7–10 | Dossiê, roteiro, voz e mídia reais em contratos persistidos |
| M4 — Edição externa | 11–12 | Projeto FilmCraft e exportação inspecionados; retomada sem duplicação |
| M5 — Revisão e aprendizado | 13–14 | Pacote validado e regra aplicada automaticamente à produção seguinte |
| M6 — Operação e piloto | 15–16 | CLI, migração, dois perfis isolados em testes e piloto longo documentado |

Dependências: 1 -> 2; 2 -> 3 -> 4 -> 5 -> 6; 6 -> 7 -> 8 -> 9 -> 10; 2 e 6 -> 11; 9, 10 e 11 -> 12; 7–12 -> 13; 4–6 e 13 -> 14; 6–14 -> 15 -> 16.

As tarefas são incrementais, mas não pressupõem trabalho de subagentes. A execução padrão deste plano é sequencial; paralelização é uma escolha posterior.

## 12. Operação esperada após implementação

Comandos abaixo são a interface proposta, ainda inexistente. Os nomes e flags fazem parte da tarefa 15. Os arquivos fornecidos pelo operador contêm idioma, nicho, provedores e orçamento; exemplos não representam credenciais reais.

```powershell
# Criar o perfil a partir de configurações explícitas.
ai-video-factory profiles create --from-file config/meu-canal.json
ai-video-factory profiles list
ai-video-factory profiles show meu-canal

# Planejar sem chamar serviços nem atualizar aprendizados.
ai-video-factory workflow run --profile meu-canal --topic "Tema do episódio" --dry-run

# Executar só pesquisa/roteiro para inspecionar as entregas.
ai-video-factory workflow run --profile meu-canal --topic "Tema do episódio" --through script

# Retomar a mesma produção até o pacote final.
ai-video-factory workflow resume --profile meu-canal --production <production-id>

# Consultar memória e registrar uma avaliação explícita.
ai-video-factory profiles memory meu-canal --stage editing
ai-video-factory profiles feedback meu-canal --production <production-id> --stage editing --note "A música encobriu a fala na abertura"

# Exportar perfil e histórico para inspeção/backup lógico.
ai-video-factory profiles export meu-canal --output output/meu-canal-memory.json
```

Detalhar backup físico consistente com a API de backup SQLite e tratamento dos arquivos de mídia na documentação de operação. Exportação JSON não substitui backup completo.

## 13. Verificação e critérios finais de aceitação

### Verificação automatizada durante a implementação

```powershell
python -m pytest tests/test_platform_support.py tests/test_workflow_models.py -q
python -m pytest tests/test_profile_store.py tests/test_profile_observations.py tests/test_memory_context.py tests/test_profile_learning.py -q
python -m pytest tests/test_staged_workflow.py tests/test_stage_research.py tests/test_stage_script.py tests/test_stage_narration.py tests/test_stage_media.py -q
python -m pytest tests/test_filmcraft_client.py tests/test_assembly_plan.py tests/test_stage_editing.py tests/test_stage_review.py -q
python -m pytest tests/test_profile_cli.py tests/test_workflow_cli.py tests/test_profile_workflow_integration.py tests/test_profile_migration.py -q
python -m pytest -q
```

Se houver alteração de contratos compartilhados com Remotion, executar `npm test` e `npm run build` dentro de `remotion/`. Não instalar todo o stack de GPU para verificar código que não depende dele.

Testes usam rede, LLM, voz e MCP injetáveis, com fixtures locais. Ensaios com FilmCraft real são uma camada separada, habilitada explicitamente, sem pressupor editor instalado na CI. Um teste que usa tom sintético ou mídia fake não comprova qualidade de narração/edição do piloto.

### Checklist de aceitação do produto

- [ ] Tema informado preservado, com pesquisa real e referências verificáveis.
- [ ] Roteiro registra fala, pausas, direção, fontes, cenas e múltiplos planos.
- [ ] Áudio real no idioma escolhido, com provedor/voz efetivos e tempos medidos.
- [ ] Mídia correspondente aos planos, direitos documentados e lacunas explícitas.
- [ ] Projeto FilmCraft editável, mídias resolvidas e exportação final 1920×1080 em 16:9.
- [ ] Episódio completo com duração medida dentro da faixa configurada; nenhuma duração comprovada somente por contagem de palavras.
- [ ] Pacote final inclui vídeo, metadados, legendas, créditos, fontes, relatórios e dependências do projeto.
- [ ] Duas execuções/perfis não compartilham preferências ou rejeições editoriais indevidamente.
- [ ] Cada estágio registra configuração efetiva, versão do perfil, resultados e evidências.
- [ ] Aprendizado pode ser avaliado e aplicado sem aprovação humana por ajuste.
- [ ] Falta de evidência mantém hipótese; falha relacionada pode suspender regra e restaurar configuração anterior.
- [ ] Produção em andamento mantém snapshot; próxima produção recebe mudanças ativas.
- [ ] Retomada não duplica itens no editor nem reutiliza etapa com entradas alteradas.
- [ ] Alterações manuais observáveis são registradas sem alegar captura contínua.
- [ ] Caminhos legados continuam utilizáveis e nenhum fluxo novo publica automaticamente.
- [ ] Piloto documenta resultados medidos, custos conhecidos, limitações e próximos ajustes.

## 14. Decisões futuras e limites desta atualização

### Adiados deliberadamente

- Calibração de música, voz, duração dos planos, número de fontes, scores e limiares de confiança.
- Escolha definitiva do nicho, idioma e identidade do primeiro canal.
- Escolha final de provedor/voz e infraestrutura de modelos conforme custo e qualidade do piloto.
- Aprendizado baseado em CTR/retenção por integração com analytics; nesta atualização, aceitar importação de feedback e observações disponíveis, sem prometer causalidade.
- Interface visual própria para perfis e painel de memória. A entrega inicial usa CLI, arquivos e relatórios.
- Renderização headless autônoma em lote, múltiplas máquinas e agendamento diário, depois da integração bridge e do piloto.
- Geração local pesada de vídeos por IA e backends adicionais de imagem/vídeo.
- Alteração da política de upload/publicação.

### Riscos concretos e tratamento

| Risco | Tratamento previsto |
|---|---|
| FilmCraft alpha ou diferença de comandos por versão | Negociação de capacidades, versão registrada, projeto curto antes do episódio longo |
| Timeout após comando aplicado | Inspeção e reconciliação antes de repetir mutações |
| Exportação com mídia offline ou encoder diferente do solicitado | Inspecionar resultado, avisos, manifesto e arquivo; registrar configuração efetiva |
| Perfil aprendendo associação sem evidência | Separar observação/hipótese/regra e exigir avaliação compatível com a proposta |
| Memória alterando o canal sem perceber | Instruções explícitas prevalecem, versões fixadas e reversão auditável |
| Histórico crescente | Resumos e consultas por contexto; originais preservados fora do prompt |
| Divergência entre SQLite, RunStore e editor | IDs idempotentes, snapshots, manifests e reconciliação no início/retomada |
| Confundir MCP com economia de recursos | Medir tempo, CPU/GPU e encoder no piloto; não prometer offload inexistente |

### Revisão deste plano antes de executar

- [x] Consolidar os seis estágios e suas entregas.
- [x] Incorporar memória em todos os estágios, com aplicação autônoma autorizada.
- [x] Separar decisões do usuário das propostas técnicas.
- [x] Reaproveitar módulos reais e apontar incompatibilidades observadas.
- [x] Definir contratos, persistência, arquivos, dependências e testes por tarefa.
- [x] Cobrir isolamento, retomada externa, snapshot, mudanças manuais e falhas de evidência/direitos.
- [x] Manter ajustes finos como trabalho posterior, conforme solicitado.
- [ ] Executar as tarefas de implementação. Este item só deve ser marcado depois da entrega e verificação do produto.

