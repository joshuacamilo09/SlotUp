# Memória Descritiva: SlotUp

## 1. Identificação

- **Nome do projeto:** SlotUp
- **Ano letivo:** 2026/2027
- **Semestre:** 5.º semestre
- **Unidade(s) curricular(es):** Projeto de Desenvolvimento de Software (com integração de Sistemas Distribuídos, Inteligência Artificial, Segurança e Engenharia de Software)
- **Docente(s):** [a preencher]

## 2. Resumo

**SlotUp: plataforma distribuída de reservas para complexos empresariais**

O SlotUp é uma plataforma web de reservas pensada para complexos empresariais, que reúne num único sistema a gestão de vários tipos de recursos e serviços partilhados. Atualmente, cada espaço ou serviço de um complexo tende a ter o seu próprio processo de reserva, muitas vezes manual, disperso e sem visibilidade global. O SlotUp responde a este problema com uma solução centralizada, segura e escalável.

A plataforma abrange três categorias de reserva: coworking (mesas e salas de reunião), estacionamento e desporto, que agrupa as sessões com personal trainer no ginásio e a quadra de padel. Apesar das diferenças entre estes serviços, todos partilham a mesma lógica essencial: um recurso, um intervalo de tempo e um utilizador. Por isso, o SlotUp assenta num núcleo de reservas genérico e extensível, que concentra as regras comuns (disponibilidade, conflitos, cancelamentos e histórico) e permite adicionar novas categorias com esforço reduzido, sem alterar o núcleo.

Quando um recurso está indisponível, o utilizador pode entrar numa fila de espera. Se a reserva for cancelada, o sistema notifica o próximo utilizador da fila e atribui-lhe a vaga, o que melhora a taxa de ocupação e a experiência de utilização.

A segurança é um pilar central do projeto. O acesso à plataforma é protegido por autenticação de dois fatores (2FA), reduzindo o risco de acessos indevidos às contas e aos dados pessoais. A gestão de permissões foi deliberadamente simplificada em dois papéis: o administrador, responsável pela configuração e supervisão do sistema, e o utilizador, que consulta a disponibilidade e gere as suas próprias reservas.

Na vertente de Inteligência Artificial, o SlotUp recorre a um Problema de Satisfação de Restrições (CSP) para atribuir reservas a recursos e intervalos de tempo. As variáveis, os domínios e as restrições do modelo (como a ausência de sobreposições e a disponibilidade de cada recurso) permitem encontrar atribuições válidas. As regras concretas do CSP ainda não estão definidas e serão estabelecidas numa fase posterior do desenvolvimento.

Do ponto de vista técnico, o SlotUp é concebido como um sistema distribuído, desenvolvido em Python e organizado em serviços que se comunicam entre si. A interface com o utilizador é disponibilizada através de uma aplicação web. A solução é empacotada em contentores Docker e orquestrada com Kubernetes, o que garante portabilidade, escalabilidade e resiliência perante falhas ou picos de procura.

O projeto integra conhecimentos de várias unidades curriculares: Sistemas Distribuídos (arquitetura, comunicação entre serviços e consistência das reservas concorrentes), Segurança (autenticação e proteção de dados), Engenharia de Software (análise de requisitos, modelação e boas práticas de desenvolvimento) e Inteligência Artificial.

## 3. Contexto

### 3.1 Problema abordado

O problema central é a organização de várias reservas interdependentes sobre recursos limitados. Num complexo empresarial, cada serviço costuma ter o seu próprio processo de reserva, sem qualquer ligação aos restantes. Um utilizador que queira, no mesmo dia, estacionar, trabalhar e praticar desporto tem de escolher um recurso e um horário para cada serviço separadamente, de forma a que as três escolhas sejam compatíveis entre si (por exemplo, o estacionamento tem de estar reservado antes de começar o período de trabalho, e a sessão de desporto não pode sobrepor-se a este).

Daqui resultam quatro problemas concretos:

- **Explosão combinatória:** o número de combinações cresce rapidamente com o número de serviços e de horários. A título de exemplo, com 10 recursos e 12 horários possíveis por serviço, cada serviço oferece 120 opções, e três serviços em conjunto geram 120³, ou seja, mais de 1,7 milhões de combinações. Para um utilizador, a escolha manual é inviável e, à medida que se acrescentam serviços, recursos e restrições, mesmo a procura exaustiva automática deixa de ser eficiente, pois o espaço de pesquisa cresce de forma exponencial.
- **Interdependência entre reservas:** as reservas de um mesmo utilizador não são independentes: se uma delas falhar ou for alterada, as restantes podem deixar de fazer sentido. Sem um mecanismo que as trate em conjunto, o utilizador fica com reservas parciais, como um lugar de estacionamento sem sala de trabalho, situações que obrigam a cancelamentos e a novas tentativas manuais.
- **Falta de explicação em caso de falha:** quando não existe solução, o utilizador recebe apenas uma recusa, sem saber o que impede a reserva. Não sabe se o problema é a falta de vagas num horário, um conflito entre dois serviços ou uma restrição de um recurso, nem que alteração (outro horário, outro recurso) permitiria avançar.
- **Concorrência:** a disponibilidade pode mudar entre a sugestão e a confirmação da reserva, porque outros utilizadores estão a reservar em simultâneo. Sem controlo adequado, isso leva a sugestões que já não são válidas no momento da confirmação ou, no pior caso, a reservas duplicadas sobre o mesmo recurso.

Estes problemas mostram a necessidade de uma solução que consiga procurar combinações válidas de forma automática, justificar o resultado e garantir a consistência das reservas perante acessos concorrentes.

### 3.2 Motivação

Com a adoção crescente de modelos de trabalho híbridos, os complexos empresariais passaram a oferecer no mesmo espaço serviços muito variados: postos de trabalho, estacionamento e atividades desportivas. Na prática, cada serviço funciona como o seu próprio sistema de reservas. Isto tem dois efeitos:

- **Para o utilizador:** tem de consultar várias plataformas e coordenar manualmente horários que dependem uns dos outros.
- **Para o gestor do complexo:** não existe uma visão unificada da ocupação dos recursos.

A motivação do projeto é responder a esta fragmentação com uma plataforma única, que simplifique a experiência do utilizador e permita ao complexo crescer, acrescentando novos serviços sem redesenhar o sistema.

### 3.3 Objetivos

**Objetivo geral:** desenvolver uma plataforma web distribuída e tolerante a falhas para a gestão de reservas num complexo empresarial, unificando num único sistema três categorias de recursos: coworking (mesas e salas), estacionamento e desporto (personal trainer e quadra de padel), e apoiando o utilizador no planeamento de várias reservas interdependentes.

**Objetivos específicos:**

1. **Planeamento com IA:** integrar um componente baseado em CSP (Problema de Satisfação de Restrições) que planeie várias reservas em simultâneo, recorrendo a backtracking, forward checking e à heurística MRV (Minimum Remaining Values).
2. **Explicação de falhas:** quando não existir solução, indicar claramente o que impede a reserva e sugerir a relaxação de uma restrição (por exemplo, um horário alternativo).
3. **Consistência e concorrência:** executar o CSP num microsserviço dedicado e confirmar as reservas através de transações na base de dados, repetindo o CSP se algum recurso deixar de estar livre entre a sugestão e a confirmação.
4. **Segurança de acesso:** garantir a segurança do acesso através de autenticação de dois fatores (2FA).
5. **Infraestrutura distribuída:** empacotar os serviços em contentores Docker e orquestrá-los com Kubernetes, garantindo portabilidade, escalabilidade e resiliência a falhas.
6. **Extensibilidade:** permitir a expansão da plataforma com novos serviços sem a necessidade de redesenhar o sistema.

## 4. Processo

### 4.1 Metodologia utilizada

O projeto segue uma **metodologia ágil**, como estudado na unidade curricular de Engenharia de Software. Em vez de planear tudo no início e só testar no fim, o trabalho é feito em ciclos curtos (sprints), melhorando o projeto aos poucos. Assim, os problemas são descobertos cedo, quando ainda é fácil corrigi-los.

Em concreto, é usada uma versão simplificada do **Scrum**, combinada com um quadro **Kanban**:

- **Sprints de cerca de 2 semanas:** no início de cada sprint, o grupo escolhe as tarefas que consegue fazer. No fim, mostra o que ficou pronto.
- **Backlog:** lista de tudo o que falta fazer, escrita como tarefas no ClickUp.
- **Quadro Kanban:** no ClickUp, com quatro colunas: A fazer, Em curso, Em revisão e Feito.
- **Reunião semanal:** para planear e rever o trabalho e tirar dúvidas.

Para o código, o grupo combinou as seguintes regras de trabalho:

- Ninguém escreve diretamente na branch `main`. Cada tarefa tem a sua branch.
- Todas as alterações entram em Pull Request, revisto por pelo menos um colega.
- Os commits são pequenos e com mensagens claras.
- Uma tarefa só está "Feita" quando o código foi revisto, os testes passam e a documentação foi atualizada. Nas tarefas de infraestrutura, também tem de ter sido testada com uma falha provocada de propósito.

### 4.2 Ferramentas utilizadas

- **Organização e colaboração:** GitHub e ClickUp
- **Desenvolvimento:** VS Code, Docker, Kubernetes e PostgreSQL
- **Testes e monitorização:** Pytest para testes do código, K6 para simular muitos utilizadores em simultâneo e Prometheus + Grafana para ver o estado do sistema em gráficos durante os testes de falha
- **Documentação e design:** Draw.io e Figma

### 4.3 Tecnologias utilizadas

- **Backend:** Python + FastAPI; SQLAlchemy + Alembic
- **Base de dados:** PostgreSQL; CloudNativePG
- **Frontend:** HTML, CSS e JavaScript + Nginx
- **Contentores e orquestração:** Docker, Docker Compose e Kubernetes
- **Segurança:** Ingress + HTTPS (TLS); TOTP (pyotp); JWT; Argon2 + AES-GCM
- **Inteligência Artificial:** algoritmo CSP
- **Notificações:** envio de email por SMTP
- **Monitorização:** Prometheus + Grafana

### 4.4 Estrutura da equipa

O grupo tem 4 elementos. Cada área do projeto tem um responsável, que coordena as decisões técnicas dessa área e responde por ela perante o grupo. No entanto, todos os elementos participam em todas as áreas: cada um escreve a documentação da sua parte, contribui para as restantes e revê o código dos colegas. Cada área conta ainda com um elemento de apoio, que acompanha o trabalho do responsável e o substitui em caso de necessidade.

| Elemento | Área | Responsável por | Apoio |
|---|---|---|---|
| Gabriel | Infraestrutura e Sistemas Distribuídos | Docker, Kubernetes, replicação da BD, testes de falha | Joshua |
| Joshua | Backend e domínio | Regras das reservas, API, controlo de concorrência | Gabriel |
| Dario | Segurança | Autenticação, 2FA, HTTPS, registo de auditoria | Edmilson |
| Edmilson | IA e frontend | Algoritmo CSP e interface web | Dario |

As decisões que afetam várias áreas são tomadas em conjunto, e a divisão de responsabilidades pode ser ajustada ao longo do projeto, conforme as necessidades da equipa.

## 5. Resultados

### 5.1 Descrição da solução desenvolvida

O SlotUp é composto por três microsserviços, cada um com uma responsabilidade bem definida, e por uma interface web servida através de Nginx. A solução está em desenvolvimento e segue a arquitetura de distribuição definida pelo grupo.

| Microsserviço | Responsabilidade | Base de dados |
|---|---|---|
| **Auth** | Contas de utilizador, perfis (administrador e utilizador), autenticação com 2FA e emissão do token de acesso | `auth_db` |
| **Booking** | Recursos, categorias, reservas, fila de espera, notificações e worker de processamento em segundo plano | `booking_db` |
| **Scheduling** | Planeamento automático de várias reservas através do CSP | Sem base de dados |

O fluxo de uma reserva múltipla decorre da seguinte forma:

1. O utilizador seleciona os serviços pretendidos e o Booking envia o pedido ao Scheduling.
2. O Scheduling executa o CSP e devolve uma combinação válida de recursos e horários, ou, se não existir, a explicação do que impede a reserva e uma alternativa.
3. O Booking confirma a combinação através de transações na base de dados.
4. Se algum recurso deixou de estar livre entre a sugestão e a confirmação, o planeamento é repetido.

As notificações por email são registadas na base de dados do Booking e enviadas pelo worker através de um servidor SMTP externo. A base de dados PostgreSQL é replicada, e todos os serviços são empacotados em contentores Docker e orquestrados com Kubernetes, com HTTPS à entrada e monitorização com Prometheus e Grafana.

### 5.2 Funcionalidades principais

**Requisitos funcionais**

| Funcionalidade | Descrição |
|---|---|
| **Gestão de utilizadores e autenticação** | Criação e gestão de contas com dois perfis, administrador e utilizador, cada um com as suas permissões. O acesso é protegido por autenticação de dois fatores (2FA). |
| **Consulta de recursos e disponibilidade** | O utilizador consulta os recursos do complexo e verifica a sua disponibilidade para uma data e horário, identificando os recursos livres antes de reservar. |
| **Gestão de reservas** | O utilizador cria, consulta, altera e cancela reservas. Cada reserva fica associada ao respetivo utilizador. |
| **Categorias de reserva** | A plataforma cobre três categorias: coworking (mesas e salas), estacionamento e desporto (ginásio com personal trainer e quadra de padel). Nas aulas de personal trainer, a reserva considera a disponibilidade do profissional e do espaço. |
| **Prevenção de conflitos e reservas duplicadas** | O sistema impede que o mesmo recurso seja reservado por utilizadores diferentes para o mesmo período, garantindo que as reservas confirmadas respeitam a disponibilidade real. |
| **Planeamento automático com IA** | O utilizador seleciona vários serviços e o sistema procura, através de um Problema de Satisfação de Restrições (CSP), uma combinação de recursos e horários que respeite as restrições existentes, recorrendo a backtracking, forward checking e à heurística MRV. |
| **Explicação de falhas e sugestão de alternativas** | Quando não existe combinação válida, o sistema indica o que impede a reserva e sugere alternativas, como outro horário ou recurso, em vez de uma simples recusa. |
| **Fila de espera** | Quando um recurso está ocupado, o utilizador pode entrar numa fila de espera. Se a reserva for cancelada, a vaga é atribuída ao próximo utilizador da fila. |
| **Notificações por email** | O utilizador recebe um email quando faz uma reserva, quando cancela uma reserva, quando entra na fila de espera e quando abre uma vaga na fila de espera. |
| **Funcionalidades do administrador** | O administrador gere utilizadores, categorias, recursos e reservas, e dispõe de um painel administrativo (dashboard) com uma visão geral da plataforma. |
| **Histórico de reservas** | O utilizador consulta as suas reservas anteriores e acompanha a sua atividade na plataforma. |

**Requisitos não funcionais**

| Característica | Descrição |
|---|---|
| **Arquitetura orientada a serviços** | O sistema é composto por vários microsserviços, entre os quais um serviço dedicado ao CSP. Os serviços são empacotados em contentores Docker e orquestrados com Kubernetes. |
| **Segurança da plataforma** | Comunicação protegida por HTTPS, autenticação com 2FA e registo de auditoria (logs) das ações relevantes. |
| **Consistência e concorrência** | As reservas são confirmadas através de transações na base de dados, garantindo consistência perante pedidos em simultâneo. |
| **Replicação dos dados** | A base de dados é replicada para evitar que uma falha isolada comprometa o funcionamento do sistema. |
| **Tolerância a falhas** | O sistema deteta falhas nos serviços e recupera automaticamente, mantendo-se disponível. A tolerância a falhas é demonstrada através de testes de falha. |
| **Monitorização e estado do sistema** | Visão geral do estado dos serviços e recursos, permitindo identificar situações que afetem o funcionamento normal. |
| **Extensibilidade** | O núcleo de reservas genérico permite acrescentar novas categorias de serviço sem redesenhar o sistema. |

**Extras e trabalho futuro**

Funcionalidades que não são prioritárias e podem ser desenvolvidas em evoluções futuras:

| Funcionalidade | Descrição |
|---|---|
| **Preferências do utilizador** | Definição de preferências de utilização, que podem tornar as sugestões do planeamento mais adequadas a cada utilizador. |
| **Código QR para reservas** | Associação de um código QR a cada reserva, para facilitar a sua apresentação no local. |
| **Exportação de reservas** | Exportação da lista de reservas do utilizador num formato externo. |
| **Estatísticas de utilização** | Indicadores sobre a utilização dos recursos, para apoiar a gestão do complexo. |
| **Sistema de favoritos** | Marcação de recursos preferidos para acesso rápido. |

### 5.3 Contributos relevantes

- **Plataforma única para serviços heterogéneos:** o núcleo de reservas genérico e extensível permite tratar coworking, estacionamento e desporto com as mesmas regras e acrescentar novas categorias sem redesenhar o sistema.
- **Planeamento conjunto de reservas interdependentes:** em vez de reservas isoladas, o utilizador obtém uma combinação coerente de vários serviços, calculada por um CSP.
- **Explicação de falhas:** quando não há solução, o sistema indica o motivo e propõe alternativas, em vez de uma simples recusa.
- **Consistência perante concorrência:** a combinação de planeamento, confirmação por transações e replaneamento automático evita reservas duplicadas e sugestões desatualizadas.
- **Arquitetura distribuída tolerante a falhas:** microsserviços, base de dados replicada e orquestração com Kubernetes, com validação planeada através de testes de falha.

## 6. Reflexão

### 6.1 Lições aprendidas

- **Definir e reduzir o âmbito cedo:** após a conversa com o docente, o âmbito foi simplificado (o restaurante saiu e o ginásio e a quadra de padel passaram a formar uma só categoria), o que tornou o projeto mais realista para o tempo disponível.
- **Ter uma arquitetura de referência única:** a divisão em serviços foi revista até ficar alinhada com o diagrama de distribuição apresentado (por exemplo, o catálogo passou a ser um módulo do Booking). Desde então, qualquer alteração que o afete é comunicada e confirmada antes de ser feita.
- **Decidir em grupo as questões em aberto:** assuntos com impacto transversal, como as notificações por email e a migração para Alembic, foram resolvidos em reunião, evitando decisões isoladas.
- **Planear antes de implementar:** definir tarefas com nome e descrição claros no ClickUp antes de começar a programar facilita a divisão do trabalho e a revisão entre colegas.

### 6.2 Limitações

- A solução encontra-se em desenvolvimento, pelo que nem todas as funcionalidades descritas estão implementadas.
- As regras concretas do CSP ainda estão em definição.
- Nesta fase, as reservas usam um intervalo livre (início e fim escolhidos pelo utilizador); horários dependentes de cada categoria ficam para uma evolução posterior.
- A plataforma é exclusivamente web, sem aplicação móvel.
- A gestão de permissões limita-se a dois papéis (administrador e utilizador), sem administradores por categoria.
- Não estão previstas reservas recorrentes nem check-in/check-out.
- As notificações limitam-se a email e a quatro eventos (fazer reserva, cancelar reserva, entrar na fila e abertura de vaga na fila).

### 6.3 Trabalho futuro

Como trabalho futuro, prevê-se o desenvolvimento do núcleo de reservas e das três categorias de serviço, a definição detalhada das restrições do CSP e a sua implementação num microsserviço dedicado, a integração da autenticação com 2FA, a implementação da replicação e dos mecanismos de tolerância a falhas, com a respetiva demonstração através de testes de falha, e a construção da interface web. Numa fase posterior, poderão ainda ser exploradas as funcionalidades extra identificadas, como as preferências do utilizador, o código QR, a exportação de reservas, as estatísticas de utilização e o sistema de favoritos, bem como horários de reserva específicos para cada categoria.