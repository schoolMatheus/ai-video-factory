# Design principal — AI Video Factory

Direção escolhida: **Espaço**, com acento **roxo midnight `#8E6BE8`**. É a versão canônica; as 21 opções em `docs/design-options/` ficam como histórico de exploração.

## Arquivos

| Arquivo | Papel |
|---|---|
| `design.md` | Especificação canônica: cores, tipografia, layout, componentes, estados e regras. |
| `tokens.css` | Contrato de tokens (cores, tipos, espaço, raio, sombra, movimento) e mapeamento para `web/src/styles/tokens.css`. |
| `producao.html` | Tela da área da produção em 1440 × 900 — referência visual da especificação. |
| `componentes.html` | Folha de componentes com todos os estados dos botões e dos planos de estágio. |

## Decisão

A tela mostra os seis estágios como planos em perspectiva: o atual à frente, os futuros recuando. Essa é a única ideia ousada — todo o resto é reto, com arestas duras e sombra sólida deslocada. O roxo aparece só no plano ativo, no botão primário e no foco.

Superfície: área da produção, estado “Roteiro em andamento”. Público: operador local que acompanha execuções longas. Progresso sempre em unidades observadas (“2 de 6 etapas concluídas”), nunca em percentual de tempo.

## Como aplicar

Este é o contrato de design, não um segundo design system. Ao implementar, os tokens entram em `web/src/styles/tokens.css` e os componentes em `web/src/components/` / `web/src/features/`, seguindo os CSS Modules existentes. Se um valor aqui conflitar com o código, o código usado pelo usuário prevalece e esta especificação deve ser atualizada.

## Nunca faça

Gradiente, glow, blur, blob, tema claro, badge decorativo, ícone em toda linha, grade de cards, percentual de progresso, animação de entrada e mais de uma superfície em perspectiva por tela.
