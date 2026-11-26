# Home do painel local — design

Data: 2026-11-26. Tamanho: médio (uma página, rotas, menu, um campo de perfil, um ajuste no contrato da API e testes).

## Intenção

Hoje quem abre o painel cai direto na lista de produções. Queremos uma home que sirva de visão geral do trabalho: o que andou nas etapas, quais nichos estão cadastrados e um lugar reservado para, no futuro, mostrar notícias desses nichos. A pessoa escolheu explicitamente não definir agora a fonte das notícias — o bloco deve existir como espaço, não como conteúdo.

## Objetivos

- Abrir o painel em uma home com produção em andamento, atividade recente, nichos e o espaço reservado de notícias.
- Usar somente dados reais que o painel já possui (produções, eventos, perfis).
- Manter o estilo canônico Espaço: hairlines, arestas duras, três tamanhos de texto, dados em mono, sem grade de cards.
- Deixar a navegação coerente: Início primeiro, Produções como página separada.

## Não objetivos

- Buscar notícias na internet, chamar `research.py`/`trend.py` ou criar endpoint de notícias.
- Exibir manchetes, fontes ou contagens inventadas para preencher o espaço reservado.
- Mudar a lógica das seis etapas, do SSE ou da área de produção.

## Anti-objetivos

- Uma home que pareça dashboard genérico com cards decorativos e números sem origem.
- Manter a lista de produções em `/` e esconder a home em um link — isso contraria a ideia de página inicial.

## Restrições

- Contrato de design em `docs/design/main`: progresso só em unidades observadas, estados vazios com orientação, nenhuma informação dependente só de cor.
- API local (`ui_backend`): `/productions`, `/productions/{id}/events` e `/profiles` já existem; não há endpoint de notícias.
- `ProfileView` não expõe `niche` hoje: o adapter descarta o campo (`profile_adapter.py:154`) e o formulário de perfil sempre envia `niche: ""`.
- Testes atuais assumem "Produções" em `/` (`App.test.tsx`, `ProductionList.test.tsx`, `production.spec.ts`, `settings.spec.ts`).

## Abordagens

- **A (escolhida): Home em `/`.** Lista de produções passa para `/producoes`; menu ganha "Início" como primeiro item. Ajustam-se router, nav e os testes que esperam a lista em `/`. Faz da home a porta de entrada real.
- **B: Home em `/inicio`.** Nada existente muda, mas quem abre o painel continua caindo na lista — contradiz a intenção de uma home.

A opção de embrulhar a home dentro da página de produções foi descartada: mistura duas funções e não entrega uma página nova.

## Como ficou decidido

- Rota `/` renderiza `Home`; `/producoes` renderiza `ProductionList`.
- Seções da home, em linhas com hairline inferior (sem caixas):
  1. **Em andamento** — produções com estado em execução (ou as mais recentes, se nenhuma estiver ativa), com título, perfil/legado, contagem de etapas concluídas e link para a área da produção.
  2. **Atividade recente** — até seis eventos da produção mais recente, via `listEvents`, com tipo, severidade em palavra e horário em mono.
  3. **Nichos cadastrados** — perfis com seu nicho quando houver; vazio mostra "Nenhum nicho cadastrado" com ação em texto para Perfis.
  4. **Notícias dos nichos** — espaço reservado com o texto "Sem fonte conectada. Espaço reservado para notícias dos nichos." Nenhuma requisição, nenhum dado de exemplo, nenhuma ação falsa.
- Estados de carregamento e erro usam as mesmas frases curtas e o `InlineError` existente; sem shimmer.

## Decisões propostas pelo builder (passíveis de correção)

- Expor `niche` em `ProfileView` (models + `_profile_view`) e registrar o contrato com `npm run generate:api`, porque sem isso a seção de nichos não tem dado real para mostrar.
- Acrescentar campo opcional "Nicho" ao formulário de cadastro de perfil, que hoje fixa `niche: ""`. Sem ele, nenhum nicho pode ser cadastrado pelo painel.
- Limitar "Atividade recente" aos eventos de uma única produção para evitar N requisições na abertura da home.

## O que fica para a implementação

- Criar `web/src/features/home/Home.tsx` e `Home.module.css`.
- Ajustar `router.tsx`, `AppShell.tsx` (menu) e os testes/e2e que dependem da rota antiga.
- Atualizar `src/ai_video_factory/ui_backend/models.py`, `profile_adapter.py`, `web/src/api/generated.ts` e os testes Python relacionados a `ProfileView`.
- Rodar `typecheck`, testes React e Python, `build`, `build_ui.py` e conferir a tela no navegador.
