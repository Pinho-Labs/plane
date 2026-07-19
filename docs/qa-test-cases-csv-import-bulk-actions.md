# Casos de teste para QA

Comentários prontos para colar nos tickets. Cada bloco lista os casos de teste
mais importantes que o QA deve validar.

---

## Ticket 1 — CSV Bulk Import for Work Items

**Casos de teste prioritários — QA**

**Template & regras**

1. Baixar template CSV → cabeçalho na ordem canônica + 1 linha de exemplo.
2. "Copiar template" e "Copiar/Baixar regras para IA" → conteúdo reflete os
   valores REAIS do projeto (estados, e-mails de membros, labels, cycles,
   módulos, estimativas, tipos). Features desabilitadas aparecem marcadas
   como "Not enabled".

**Validação (dry-run) — nada é gravado**

3. CSV válido → contadores "X prontas / 0 com erro" corretos e NENHUMA issue
   criada no projeto.
4. Erros por linha reportados com nº da linha e motivo:
   - Nome vazio / > 255 caracteres
   - Estado inexistente no projeto
   - Responsável que não é membro ativo (por e-mail)
   - Prioridade inválida
   - Data mal formatada / Start Date > Target Date
   - Parent (PROJ-N) inexistente
   - Estimate/Cycle/Module/Work Item Type quando a feature está DESABILITADA
   - Label inexistente com usuário NÃO-admin

**Prévia (tabela)**

5. Cada linha válida é renderizada como um work item real: pílula de estado com
   cor, avatares de responsáveis, labels coloridas, datas, estimativa, ciclo,
   módulos e tipo; ícone de descrição quando a descrição está preenchida.
6. Abas **Todas / Válidas / Com erro** filtram as linhas e os contadores por aba
   batem com os totais.
7. Busca por nome filtra as linhas da tabela.
8. Linhas inválidas aparecem na tabela (abas Todas / Com erro) com o valor
   digitado e o motivo do erro; o campo que falhou vem destacado.
9. Colunas **#** e **Nome** ficam fixas (sticky) e as demais rolam na horizontal.
10. Colunas Estimativa / Ciclo / Módulos / Tipo só aparecem quando a respectiva
    feature está habilitada no projeto.
11. Paginação a 25 linhas por página, com navegação anterior/próxima.
12. Arquivo com > 200 linhas válidas → banner "primeiras 200 de N" e a tabela
    mostra só a amostra; ainda assim TODAS as válidas são importadas no commit.

**Commit (gravação)**

13. Import feliz → issues criadas com sequence_id contínuo (PROJ-N sem furos),
    responsáveis, labels, cycle e módulos vinculados.
14. Toggle "pular linhas inválidas": válidas criadas, inválidas ignoradas com
    relatório de erros; e o modo "bloquear até limpo".
15. Auto-criação de label: ADMIN cria label nova automaticamente; NÃO-admin
    recebe erro na linha.
16. Dedupe por External ID → reimportar o mesmo arquivo NÃO duplica.

**Assíncrono & limites**

17. Arquivo > 200 linhas → import enfileirado (202), página de histórico em
    Settings → Imports atualiza o status até "completed".
18. > 5000 linhas ou > 5 MB → rejeitado com mensagem clara (413/400).

**Permissão & pontos de entrada**

19. Não-membro / role viewer → 403 (não consegue importar).
20. Botão "Import" aparece no header de work items e também nas listas de
    cycle, module e view; pré-seleciona e trava o projeto atual.

**Descrição** (ver ticket relacionado): HTML é sanitizado e renderizado;
markdown NÃO é interpretado (aparece literal).

---

## Ticket 2 — Adicionar bulk actions na página de itens de trabalho

**Casos de teste prioritários — QA**

**Seleção & toolbar**

1. Selecionar 1+ itens → toolbar fixa aparece no rodapé com contador correto
   ("N selecionados"). Botão X limpa a seleção.
2. Funciona nos layouts List, Spreadsheet e Gantt.

**Aplicação em massa (todos os itens selecionados)**

3. Alterar Estado → todos os itens selecionados mudam de estado.
4. Alterar Prioridade → aplicada a todos.
5. Responsáveis (multi) e Labels (multi) → aplicados a todos.
6. Start Date e Target Date → aplicados a todos; validar coerência
   start ≤ target.
7. Cycle → itens adicionados ao cycle escolhido (método em lote).
8. Módulos (multi) → adicionados a cada item selecionado.

**Feature flags (dropdowns condicionais)**

9. Cycle só aparece se o projeto tem cycles habilitado; Módulos só com módulos
   habilitados; Estimate só com estimativas habilitadas.

**Feedback & robustez**

10. Durante o update a toolbar fica bloqueada (sem clique duplo / opacidade
    reduzida).
11. Toast de sucesso mostra a contagem; em falha, toast de erro.
12. Efeitos colaterais preservados: activity log, notificações e webhooks
    disparam para cada item (mesma via do editor individual).

**Bulk delete**

13. Excluir em massa → modal de confirmação; ao confirmar, todos os itens
    selecionados são removidos.

**Permissão**

14. Usuário sem permissão de edição não consegue usar a toolbar.

---

## Ticket 3 — Regras de IA: descrição aceita HTML/markdown

**Casos de teste prioritários — QA**

**Documento de regras (endpoint `.../import-csv/rules/`)**

1. A seção "Description" indica que HTML é aceito e sanitizado, e que markdown
   NÃO é interpretado (contém "Markdown is NOT interpreted").

**Comportamento real da descrição no import**

2. HTML válido (`<p>`, `<b>`/`<i>`, listas `<ul><li>`, links, code) → item
   criado com a descrição formatada.
3. HTML com tags/atributos não permitidos → sanitizado (tags perigosas
   removidas), sem quebrar o item.
4. Texto plano (ex.: `a < b & c`) → escapado e envolto em `<p>`; caracteres
   `<`, `>` e `&` aparecem literalmente, sem virar HTML.
5. Markdown (ex.: `**negrito**` ou `# Título`) → aparece LITERAL, confirmando
   que não há conversão de markdown.
6. Valor começando com `<` é tratado como HTML; qualquer outro é tratado como
   texto plano.
