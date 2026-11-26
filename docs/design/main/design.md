# Design principal — Espaço (roxo midnight)

Especificação canônica da interface da área de produção. Canvas de referência: **1440 × 900 px**. Posições em `x` (esquerda), `y` (topo), `largura × altura`.

Superfície: área da produção, estado “Roteiro em andamento”. Público: operador local que acompanha execuções longas. Conteúdo real: seis estágios, produção `prd_04f2`, tema “Europa's Hidden Ocean”, pt-BR. Progresso só em unidades observadas (“2 de 6 etapas concluídas”).

## 1. Cores

| Token | Hex | HSL | Uso |
|---|---|---|---|
| `bg` | `#0A0A0B` | 0°, 4%, 4% | fundo da aplicação |
| `plane` | `#161618` | 0°, 4%, 9% | planos dos estágios |
| `plane-2` | `#1F1F22` | 240°, 4%, 13% | plano atual |
| `text` | `#F5F5F2` | 60°, 12%, 95% | texto primário |
| `muted` | `#A2A29E` | 60°, 2%, 63% | texto de apoio |
| `hair` | `#2A2A2D` | 240°, 4%, 17% | hairlines de 1 px e bordas de planos futuros |
| `accent` | `#8E6BE8` | 257°, 73%, 66% | plano atual, botão primário, foco |
| `shadow` | `4px 4px 0 #000000` | — | sombra sólida dos planos e botões |

Contraste verificado: `accent` sobre `bg` = 5,11:1; `bg` sobre `accent` = 5,11:1; `muted` sobre `bg` = 7,73:1. Todos acima de 4,5:1.

### Estados derivados do acento

| Estado | Valor |
|---|---|
| Hover do primário | `#A98AF0` |
| Pressionado do primário | `#8769D9` + `translate(2px,2px)` + sombra `2px 2px 0 #000` |
| Primário desabilitado | fundo `#2C243A`, texto `#A295B8`, motivo sempre visível |
| Foco | outline 2 px `accent`, offset 2 px |

## 2. Tipografia

Três tamanhos por tela. Pesos 400 e 500. Mono apenas para dados (IDs, contagens, timecodes).

| Papel | Família | Tamanho / altura | Peso | Tracking |
|---|---|---|---|---|
| Display | Space Grotesk | 48 px / 1,05 | 500 | −0,04em |
| Corpo | DM Sans | 15 px / 1,55 / máx. 66 caracteres | 400 | normal |
| Pequeno | DM Sans | 13 px / 1,45 | 400 | normal |
| Dados | Space Mono | 13 px / 1,45 | 400 | normal |

Stacks: `'Space Grotesk', 'Segoe UI', sans-serif`; `'DM Sans', system-ui, sans-serif`; `'Space Mono', ui-monospace, Consolas, monospace`.

## 3. Espaço

Escala única: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64. Raios: 0 (arestas duras). Mais espaço entre grupos do que dentro deles. Nenhuma superfície arredondada.

## 4. Layout (1440 × 900)

| Elemento | x | y | Tamanho | Detalhe |
|---|---|---|---|---|
| Barra superior | 0 | 0 | 1440 × 64 | borda inferior 1 px `hair` |
| Wordmark | 32 | 22 | — | DM Sans 15 / 500 |
| Tema na barra | 200 | 23 | — | DM Sans 13 `muted` |
| Botão secundário | 1124 | 8 | 120 × 48 | raio 0, borda 1 px `#3A3A3D`, sombra sólida |
| Botão primário | 1256 | 8 | 160 × 48 | raio 0, fundo `accent`, texto `bg`, sombra sólida |
| Pilha de estágios | 56 | 120 + i·96 | 320 × 72 | `perspective(900px) rotateY(10deg) translateZ(…)` |
| Plano atual | 56 | 216 | 320 × 72 | `translateZ(0)`, fundo `plane-2`, borda 2 px `accent` |
| Planos futuros | 56 | 312 / 408 / 504 / 600 | 320 × 72 | `translateZ(-80/-140/-200/-260px)`, opacidade 0,55 / 0,35 / 0,22 / 0,16 |
| Título display | 440 | 120 | 640 × 56 | Space Grotesk 48 / 500 |
| Subtítulo | 440 | 180 | — | DM Sans 13 `muted` + ID em Space Mono |
| Coluna “Fala” | 440 | 232 | 312 × 420 | corpo 15 px |
| Coluna “Direção” | 776 | 232 | 312 × 420 | corpo 15 px; gutter 24 px |
| Lista de artefatos | 1120 | 120 | 288 × 620 | linhas de 64 px com hairline inferior |

A perspectiva existe apenas na pilha de estágios. O resto da tela é plano e reto.

## 5. Componentes

### Botão primário
160 × 48; raio 0; fundo `accent`; texto `bg` 15 px/400; borda 1 px `accent`; sombra `4px 4px 0 #000`. Rótulo descreve a ação (“Continuar”, “Retomar etapa”) e mantém o nome ao longo do fluxo. Loading preserva o rótulo e acrescenta spinner de 14 px à esquerda, com largura travada.

### Botão secundário
120 × 48; raio 0; fundo transparente; borda 1 px `#3A3A3D`; mesma sombra sólida. Hover = fundo `plane`.

### Plano de estágio
320 × 72; fundo `plane`; borda 1 px `hair`; quadrado de 8 px à esquerda; rótulo 15 px; estado em Space Mono 13 à direita. Concluído = quadrado vazio com borda `muted` + palavra “concluída”. Atual = borda 2 px `accent`, quadrado preenchido `accent` + palavra “ativo”. Futuro = borda `hair` + palavra “não iniciada”.

### Lista de artefatos
Linhas de 64 px separadas por hairline; sem caixa, sem badges, sem ícones. Estado sempre em palavra (“pronto”, “pendente”).

### Estados de conteúdo
- **Vazio:** “Nenhum artefato neste estágio” + ação em texto sublinhado.
- **Carregando:** mesma estrutura, com uma frase curta no lugar do dado. Sem shimmer.
- **Erro:** hairline inferior `accent` + palavra “falhou” + uma frase com o que fazer. Nunca só cor.

## 6. Movimento e acessibilidade

Transição de 150 ms ease-out apenas quando o estágio ativo muda. `prefers-reduced-motion` desliga a transição e a perspectiva volta a `none`. Todos os alvos ≥ 44 px, foco visível em 2 px, navegação por teclado completa. Nenhuma informação depende só de cor.

## 7. Responsivo

Abaixo de 1100 px: a pilha de estágios vira lista horizontal com scroll; as colunas “Fala” e “Direção” empilham; artefatos descem abaixo do conteúdo. Texto nunca abaixo de 13 px.

## 8. Fora do escopo

Gradiente, glow, blur, blob, tema claro, badge decorativo, ícone em toda linha, grade de cards, percentual de progresso, animação de entrada, mais de uma superfície em perspectiva por tela.
