# Tarefa: tela "Detalhe do recurso" (`recurso.html`)

Este documento explica tudo o que é preciso para fazer esta tela.
Pode ser enviado inteiro para uma IA como contexto.

## 1. Contexto

O SlotUp é uma plataforma de reservas para um complexo empresarial, com três
categorias: Coworking (mesas e salas), Estacionamento e Desporto (ginásio,
personal trainer, padel). Backend em Python/FastAPI (microserviços auth e
booking), frontend em **HTML, CSS e JavaScript puros**, servido pelo Nginx.

Esta tela é onde o utilizador escolhe **dia e horário** de um recurso e faz a
reserva. Chega-se a ela pela lista da categoria (`categoria.html`).

## 2. Regras do frontend

- **Sem frameworks e sem bibliotecas novas** (nada de React, Bootstrap, jQuery).
- Textos da **interface em português de Portugal**, como no design
  ("utilizador", "palavra-passe", "Reservado por si").
- Comentários no código em português, explicando o que cada parte faz.
- **Todo texto que vier de dados** (nomes, locais, tags) entra no HTML através
  da função `esc()` do `js/api.js`, para evitar XSS.
- **Sem JavaScript dentro do HTML** (`<script>` com código ou `onclick=""`):
  todo o JS fica em `js/recurso.js`.
- Usar as variáveis de cor de `css/style.css` (`--cor-primaria`, `--cor-borda`,
  `--cor-texto-suave`, `--raio`, `--fonte-mono`...). Não escrever cores soltas
  que já existam como variável.

## 3. Arquivos

| Arquivo | O que fazer |
|---|---|
| `recurso.html` | **Criar** |
| `css/recurso.css` | **Criar**: estilos só desta tela |
| `css/componentes.css` | **Criar**: peças reutilizáveis noutras telas (ver secção 6) |
| `js/recurso.js` | **Criar** |
| `css/style.css`, `js/api.js`, `index.html` | **Não alterar**. Se precisar de algo, falar com o Gabriel |

Estrutura do `<head>` e do fim do `<body>` (copiar do `index.html` as fontes
Plus Jakarta Sans, IBM Plex Mono e Material Symbols Rounded):

```html
<link rel="stylesheet" href="css/style.css">
<link rel="stylesheet" href="css/componentes.css">
<link rel="stylesheet" href="css/recurso.css">
...
<body>
  <div id="cabecalho"></div>          <!-- o js/layout.js desenha o cabeçalho aqui -->
  <main class="conteudo"> ... </main>
  <script src="js/api.js"></script>
  <script src="js/layout.js"></script> <!-- enquanto não existir, a página fica sem cabeçalho: normal -->
  <script src="js/recurso.js"></script>
</body>
```

No início do `js/recurso.js`: `const utilizador = requireAuth();` (sem sessão,
vai para o login). O email do utilizador está em `utilizador.email`.

## 4. Como testar

Na pasta `infra/docker`: `docker compose up -d`, depois abrir
`http://localhost:8080/login.html`, entrar, e abrir
`http://localhost:8080/recurso.html?id=1`.
Ao editar HTML/CSS/JS basta recarregar a página (Cmd+Shift+R).

A tela lê da URL o recurso, o dia e o horário:
`recurso.html?id=<id>&dia=AAAA-MM-DD&inicio=HH:MM&fim=HH:MM`
(usar `new URLSearchParams(location.search)`). Sem `dia`, usa hoje; sem
`inicio`/`fim`, usa a próxima hora cheia com 1 hora de duração.
A lista da categoria abre esta tela já com estes valores.

## 5. O que a tela tem (design)

Layout em duas colunas que passam a uma só em ecrã estreito:
coluna principal `flex: 999 1 480px` e painel lateral `flex: 1 1 300px`,
`gap: 28px`. O painel lateral fica fixo ao rolar (`position: sticky; top: 84px`).

**a) Caminho** (13px, cor `--cor-texto-suave`):
`Início / Coworking / Sala Atlântico`. "Início" leva a `index.html`, a
categoria leva a `categoria.html?cat=<categoria>`, o último fica a negrito.

**b) Cabeçalho do recurso**: caixa do ícone 72×72px (raio `--raio`, ícone 34px,
cores da categoria: `--coworking` / `--coworking-suave`, etc.); nome
(`clamp(22px, 3vw, 28px)`, peso 800); etiqueta da categoria (pílula 12px, peso
700, mesmas cores); local (14px, cinza); tags (12px, peso 600, borda
`--cor-borda`, raio `--raio-pequeno`).

**c) Dias**: grelha de 7 botões (`repeat(7, minmax(0, 1fr))`, `gap: 6px`), de
hoje até daqui a 6 dias. Cada um com dia da semana (12px, peso 700) e número
(18px, peso 800). O dia escolhido fica escuro (fundo --cor-texto, texto branco).

**d) Grelha do dia**: cartão branco com as horas **08:00 a 20:00**,
**48px por hora** (altura total 576px). As horas ficam à esquerda (12px, mono,
cinza, numa margem de 52px), com uma linha por hora. Clicar numa hora move a
seleção para essa hora, mantendo a duração. Por cima da grelha, blocos
posicionados com `position: absolute` (`top = (hora - 8) * 48`):
- **Ocupado**: riscado diagonal
  `repeating-linear-gradient(135deg, #EEF0F3 0 3px, #DFE2E8 3px 6px)`,
  texto cinza, "Ocupado" + horário.
- **Ocupado · está na fila**: fundo `--cor-fila-suave`, borda `1.5px dashed var(--cor-fila)`.
- **A sua reserva**: fundo `--cor-primaria`, texto branco.
- **Seleção**: borda `2px solid var(--cor-primaria)`, fundo com 12% da cor
  primária, texto "Seleção" + horário; anima `top` e `height` em 0.15s.
- **Linha de agora** (só se o dia for hoje): linha vermelha `#E5484D` de 2px com
  uma bolinha à esquerda.
Por baixo: "Clique numa hora para a selecionar; ajuste início e fim no painel."

**e) Painel "Nova reserva"** (cartão com sombra `0 8px 24px rgba(20,22,31,.06)`):
- Título "Nova reserva" (17px, peso 800).
- Caixa com ícone `calendar_today` e o dia por extenso.
- Dois seletores lado a lado, **Início** e **Fim**: botão `remove`, horário
  (15px, mono), botão `add`. Altura 44px, borda `--cor-borda-forte`.
- Mensagem de estado (13px, peso 700, com ícone):
  - livre: `check_circle` "Disponível · 1h30" (fundo 14% de `--cor-livre`, texto `#15803D`)
  - ocupado: `error` "Ocupado neste intervalo" (cores da fila)
  - já está na fila: `hourglass_top` "Ocupado · já está na fila"
  - reserva sua: `event_available` "Já tem uma reserva aqui" (cores primárias)
- Botão principal (48px): "Reservar 09:00–10:30" / "Ver alternativas" /
  "Ver as minhas reservas", conforme o estado.
- Nota: ícone `mail` + "Enviamos a confirmação para <email do utilizador>".

**f) Legenda** (cartão pequeno, 2 colunas): Livre, Ocupado (riscado),
Reservado por si (primária), Em fila (tracejado laranja).

**g) Janela "Reserva confirmada"** (abre depois de reservar): ícone `check`
num círculo verde 56px; título "Reserva confirmada" (24px, peso 800);
"Enviámos os detalhes para <email>"; tabela com Recurso, Data, Horário (mono)
e Código (mono); botões "Fechar" e "Ver as minhas reservas" (`reservas.html`).

**h) Janela "Este horário já está ocupado"** (abre com "Ver alternativas"):
ícone `event_busy`; nome + quando; secção `auto_awesome` "Sugestões para o seu
pedido" com opções escolhíveis (nome · etiqueta, detalhe, horário); caixa
laranja tracejada "Prefere este horário? Entre na fila." com botão
"Entrar na fila"; botões "Alterar pedido" e "Reservar sugestão".

Janelas: fundo escuro `rgba(14,16,21,.5)` em ecrã inteiro, cartão branco
centrado (máx. 460px a confirmação, 600px o conflito), raio `calc(var(--raio) + 4px)`,
sombra `0 24px 60px rgba(0,0,0,.3)`. Fechar com o X, com Esc e clicando fora.

## 6. Componentes reutilizáveis (`css/componentes.css`)

Este arquivo já existe (criado na lista da categoria) e já tem: `.caminho`,
`.abas`/`.aba`, `.chips-dias`/`.chip-dia`, `.seletor-hora`, `.pilula`
(`.livre`, `.ocupado`, `.minha`, `.fila`) e `.interruptor`. **Usar estes** em vez
de criar novos. Os chips de dia e o seletor do detalhe são um pouco maiores no
design: ajustar o tamanho em `css/recurso.css`, sem mudar o componente.

Acrescentar **no fim** de `componentes.css` só o que ainda não existe:
- `.modal` (fundo + cartão da janela)
- `.estado` (a mensagem com ícone: `.estado.livre`, `.estado.ocupado`...)

Cores novas já disponíveis em `style.css`: `--cor-livre-texto`,
`--cor-livre-suave`, `--cor-ocupado`, `--cor-ocupado-claro`.

## 7. Regras de horário (iguais às do backend)

- Os horários andam de **15 em 15 minutos** (o design usa 30, mas o backend exige múltiplos de 15).
- Duração mínima: **15 minutos**. O fim tem de ser depois do início.
- Tudo dentro do horário de abertura (para já **08:00–20:00**).
- **Não se pode reservar no passado** (se o dia for hoje, o início não pode ser antes de agora).
- No máximo **30 dias** à frente.
- Horas sem fuso: valem como hora local do complexo.

## 8. Dados fictícios (por agora)

A tela ainda **não liga à API**. Todos os dados falsos ficam **num único objeto no
topo do `js/recurso.js`**, para depois ser trocado por chamadas à API. Os nomes
dos campos são provisórios e vão ser alinhados com o booking-service:

```js
const DADOS_FALSOS = {
  recurso: { id: 1, name: "Sala Atlântico", category: "coworking", type: "Salas de reunião",
             location: "Piso 2", capacity: "até 8 pessoas", tags: ["Ecrã", "Videoconferência"], icon: "groups" },
  ocupados:   [{ start: "09:00", end: "10:30" }, { start: "13:00", end: "14:30" }],
  minhas:     [{ start: "16:00", end: "17:00" }],
  naFila:     [],
  sugestoes:  [{ name: "Sala Índico", tag: "Mesmo horário", sub: "Piso 2 · até 8 pessoas", time: "09:00–10:30" }],
};
```

"Reservar" com estado livre: acrescenta o horário a `minhas`, redesenha a grelha
e abre a janela de confirmação (código fictício, ex.: `SU-48213`).

## 9. Fora do escopo desta tarefa

- Ligação real à API (vem depois, com os nomes de campos definitivos).
- Sugestões reais: vêm do serviço de scheduling (CSP), na 3.ª entrega. Por agora são fictícias.
- Cabeçalho e menu do perfil (são do `js/layout.js`).

## 10. Pronto quando

- [ ] A tela fica igual ao design em ecrã largo e funciona no modo responsivo do F12 (largura 390px).
- [ ] Trocar o dia, clicar numa hora e usar os + / − atualiza a seleção, a mensagem e o botão.
- [ ] As regras da secção 7 são respeitadas (os botões + / − não deixam passar dos limites).
- [ ] Reservar abre a confirmação e o bloco "A sua reserva" aparece na grelha.
- [ ] Horário ocupado → "Ver alternativas" abre a janela de conflito.
- [ ] As janelas fecham com X, Esc e clique fora.
- [ ] Sem erros no Console do F12.
- [ ] Sem JS dentro do HTML; textos de dados passam por `esc()`.

## 11. Git

Trabalhar na branch `frontend-detalhe-recurso`. Commits pequenos, com mensagem
a dizer o que mudou. No fim, abrir um Pull Request para o Gabriel rever.
Apagar este arquivo antes do merge.