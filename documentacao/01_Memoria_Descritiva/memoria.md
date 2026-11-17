# Memória Descritiva: SlotUp

## 1. Identificação

- **Nome do projeto:** SlotUp
- **Ano letivo:** 2026/2027
- **Semestre:** 5.º semestre
- **Unidade(s) curricular(es):** Projeto de Desenvolvimento de Software (com integração de Sistemas Distribuídos, Inteligência Artificial, Segurança e Engenharia de Software)
- **Docente(s):** Miguel Boavida, Pedro Rosa, Rui Ramos, Sérgio Nunes e Samuel Gomes

## 2. Resumo

**SlotUp: plataforma distribuída de reservas para complexos empresariais**

O SlotUp é uma plataforma web de reservas pensada para complexos empresariais, que reúne num único sistema a gestão de vários tipos de recursos e serviços partilhados. Atualmente, cada espaço ou serviço de um complexo tende a ter o seu próprio processo de reserva, muitas vezes manual, disperso e sem visibilidade global. O SlotUp responde a este problema com uma solução centralizada, segura e escalável.

A plataforma abrange três categorias de reserva: coworking (mesas e salas de reunião), estacionamento e desporto, que agrupa as sessões com personal trainer no ginásio e a quadra de padel. Apesar das diferenças entre estes serviços, todos partilham a mesma lógica essencial: um recurso, um intervalo de tempo e um utilizador. Por isso, o SlotUp assenta num núcleo de reservas genérico e extensível, que concentra as regras comuns (disponibilidade, conflitos, cancelamentos e histórico) e permite adicionar novas categorias com esforço reduzido, sem alterar o núcleo.

Quando um recurso está ocupado, o utilizador pode entrar numa fila de espera. Se uma reserva for cancelada, a vaga é oferecida ao primeiro da fila, que tem quinze minutos para a aceitar, o que melhora a taxa de ocupação e a experiência de utilização.

A segurança é um pilar central do projeto. O acesso à plataforma é protegido por autenticação de dois fatores (2FA), reduzindo o risco de acessos indevidos às contas e aos dados pessoais. A gestão de permissões foi deliberadamente simplificada em dois papéis: o administrador, responsável pela configuração e supervisão do sistema, que também pode fazer reservas, e o utilizador, que consulta a disponibilidade e gere as suas próprias reservas.

Na vertente de Inteligência Artificial, o SlotUp recorre a um Problema de Satisfação de Restrições (CSP) para planear várias reservas em conjunto, procurando uma combinação de recursos e horários que respeita as regras do complexo. Nesta fase já existe um protótipo funcional, com backtracking, forward checking e a heurística MRV, que será integrado no fluxo de reservas na fase seguinte.

Do ponto de vista técnico, o SlotUp é um sistema distribuído, desenvolvido em Python e organizado em três microsserviços (autenticação, reservas e scheduling), com bases de dados próprias nos serviços de autenticação e de reservas, e com uma aplicação web como interface. Nesta fase, os serviços correm em contentores Docker, em dois servidores: o Nginx encaminha os pedidos para o servidor 1 e, se este falhar, para o servidor 2, sem erro para o utilizador. Na fase seguinte, a solução passa para Kubernetes, com a base de dados replicada.

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

**Objetivo geral:** desenvolver uma plataforma web distribuída e tolerante a falhas para a gestão de reservas num complexo empresarial, unificando num único sistema as três categorias de recursos: coworking (mesas e salas), estacionamento e desporto (personal trainer e quadra de padel), e apoiando o utilizador no planeamento de várias reservas interdependentes.

**Objetivos específicos:**

1. **Planeamento com IA:** integrar um componente baseado em CSP (Problema de Satisfação de Restrições) que planeie várias reservas em simultâneo, recorrendo a backtracking, forward checking e à heurística MRV (Minimum Remaining Values).
2. **Explicação de falhas:** quando não existir solução, indicar claramente o que impede a reserva e sugerir a relaxação de uma restrição (por exemplo, um horário alternativo).
3. **Consistência e concorrência:** executar o CSP num microsserviço dedicado e confirmar as reservas através de transações na base de dados, repetindo o CSP se algum recurso deixar de estar livre entre a sugestão e a confirmação.
4. **Segurança de acesso:** garantir a segurança do acesso através de autenticação de dois fatores (2FA).
5. **Infraestrutura distribuída:** empacotar os serviços em contentores Docker, com réplicas e failover já nesta fase, e orquestrá-los com Kubernetes na fase seguinte, garantindo portabilidade, escalabilidade e resiliência a falhas.
6. **Extensibilidade:** permitir a expansão da plataforma com novos serviços sem a necessidade de redesenhar o sistema.

## 4. Processo

### 4.1 Metodologia utilizada

Usamos uma **metodologia ágil**, como visto na unidade curricular de Engenharia de Software. Em vez de planear tudo no início e só testar no fim, trabalhamos em ciclos curtos (sprints) e vamos melhorando o projeto aos poucos. Assim descobrimos os problemas cedo, quando ainda é fácil corrigi-los.

Em concreto, usamos uma versão simplificada do **Scrum**, combinada com um quadro **Kanban**:

- **Sprints de cerca de 2 semanas:** no início de cada sprint, o grupo escolhe as tarefas que consegue fazer. No fim, mostramos o que ficou pronto.
- **Backlog:** é a lista de tudo o que falta fazer, escrita como tarefas no ClickUp.
- **Quadro Kanban:** no ClickUp, com quatro colunas: A fazer, Em curso, Em revisão e Feito.
- **Reunião semanal:** para planear e rever o trabalho e tirar possíveis dúvidas.

Para o código, combinámos as seguintes regras de trabalho:

- Ninguém escreve diretamente na branch `main`. Cada tarefa tem a sua branch.
- Todas as alterações entram em Pull Request, revisto por pelo menos um colega.
- Os commits são pequenos e com mensagens claras.
- Uma tarefa só está "Feita" quando o código foi revisto, os testes passam e a documentação foi atualizada. Nas tarefas de infraestrutura, também tem de ter sido testada com uma falha provocada de propósito.

### 4.2 Ferramentas utilizadas

- **Organização e colaboração:** GitHub e ClickUp
- **Desenvolvimento:** VS Code, Docker, Docker Compose e PostgreSQL (Kubernetes na terceira entrega)
- **Testes e monitorização:** Pytest para testes do código. Na terceira entrega, K6 para simular muitos utilizadores ao mesmo tempo e Prometheus + Grafana para ver o estado do sistema em gráficos durante os testes de falha
- **Documentação e design:** Draw.io e Figma

### 4.3 Tecnologias utilizadas

- **Backend:** Python + FastAPI; SQLAlchemy + Alembic
- **Base de dados:** PostgreSQL; CloudNativePG (terceira entrega)
- **Frontend:** HTML, CSS e JavaScript + Nginx
- **Contentores e orquestração:** Docker + Docker Compose; Kubernetes (terceira entrega)
- **Segurança:** TOTP (pyotp); JWT; Argon2 + AES-GCM; Ingress + HTTPS com TLS (terceira entrega)
- **Inteligência Artificial:** algoritmo CSP (protótipo)
- **Notificações:** envio de email por SMTP (terceira entrega)
- **Monitorização:** Prometheus + Grafana (terceira entrega)

### 4.4 Estrutura da equipa

O grupo tem 4 elementos. Cada área do projeto tem um responsável, que coordena as decisões técnicas dessa área e responde por ela perante o grupo. No entanto, todos os elementos participam em todas as áreas: cada um escreve a documentação da sua parte, contribui para as restantes e revê o código dos colegas. Cada área conta ainda com um elemento de apoio, que acompanha o trabalho do responsável e o substitui em caso de necessidade.

| Elemento | Área | Responsável por | Apoio |
|---|---|---|---|
| Gabriel | Infraestrutura e Sistemas Distribuídos | Docker, Kubernetes, replicação da BD, testes de falha | Joshua |
| Joshua | Backend e domínio | Regras das reservas, API, controlo de concorrência | Gabriel |
| Dário | Segurança | Autenticação, 2FA, HTTPS, registo de auditoria | Edmilson |
| Edmilson | IA e frontend | Algoritmo CSP e interface web | Dário |

As decisões que afetam várias áreas são tomadas em conjunto, e a divisão de responsabilidades pode ser ajustada ao longo do projeto, conforme as necessidades da equipa.

## 5. Resultados

### 5.1 Descrição da solução desenvolvida

O SlotUp é composto por três microsserviços, cada um com uma responsabilidade bem definida, e por uma interface web servida através de Nginx. Nesta segunda fase, o projeto passou do desenho à implementação.

| Microsserviço | Responsabilidade | Base de dados | Estado (2.ª entrega) |
|---|---|---|---|
| **Auth** | Contas de utilizador, perfis (administrador e utilizador), autenticação com 2FA e emissão do token de acesso | `auth_db` | Em funcionamento |
| **Booking** | Recursos, categorias, reservas, fila de espera, notificações e worker de processamento em segundo plano | `booking_db` | Em funcionamento. Os pedidos de email já ficam guardados; o envio fica para a 3.ª entrega |
| **Scheduling** | Planeamento automático de várias reservas através do CSP | Sem base de dados | Protótipo funcional, ainda fora do fluxo de reservas |

Os serviços correm em contentores Docker, geridos com Docker Compose, em dois servidores. O Nginx encaminha os pedidos para o servidor 1 e, se este falhar, para o servidor 2, sem erro para o utilizador, e healthchecks verificam o estado dos serviços. Na fase seguinte, a solução passa para Kubernetes no Azure, com HTTPS, com a base de dados PostgreSQL replicada através do CloudNativePG e com monitorização em Prometheus e Grafana.

Quando o CSP for integrado no fluxo de reservas (3.ª entrega), o planeamento de várias reservas decorrerá da seguinte forma:

1. O utilizador seleciona os serviços pretendidos e o Booking envia o pedido ao Scheduling.
2. O Scheduling executa o CSP e devolve uma combinação válida de recursos e horários ou, se não existir, a explicação do que impede a reserva e uma alternativa.
3. O Booking confirma a combinação através de transações na base de dados.
4. Se algum recurso deixou de estar livre entre a sugestão e a confirmação, o planeamento é repetido.

As notificações por email serão registadas na base de dados do Booking e enviadas pelo worker através de um servidor SMTP externo. Nesta fase, os pedidos já ficam guardados e falta o envio.

### 5.2 Funcionalidades principais

**Requisitos funcionais**

| Funcionalidade | Descrição | Estado (2.ª entrega) |
|---|---|---|
| **Gestão de utilizadores e autenticação** | Criação e gestão de contas com dois perfis, administrador e utilizador, cada um com as suas permissões. O acesso é protegido por autenticação de dois fatores (2FA). | **Parcial.** Registo, login com 2FA e dois perfis. O bloqueio por tentativas e a recuperação de palavra-passe ficam para a 3.ª entrega. |
| **Consulta de recursos e disponibilidade** | O utilizador consulta os recursos do complexo e verifica a sua disponibilidade para uma data e horário, identificando os recursos livres antes de reservar. | **Parcial.** API e páginas inicial e de administração. As páginas de categoria e de recurso ainda usam dados fictícios. |
| **Gestão de reservas** | O utilizador cria, consulta, altera e cancela reservas. Cada reserva fica associada ao respetivo utilizador. | **Parcial.** Criar, consultar e cancelar. Alterar uma reserva fica para a 3.ª entrega. |
| **Categorias de reserva** | A plataforma cobre três categorias: coworking (mesas e salas), estacionamento e desporto (ginásio com personal trainer e quadra de padel). Nas aulas de personal trainer, a reserva considera a disponibilidade do profissional e do espaço. | **Parcial.** As três categorias estão criadas. A disponibilidade conjunta do profissional e do espaço fica para a 3.ª entrega. |
| **Prevenção de conflitos e reservas duplicadas** | O sistema impede que o mesmo recurso seja reservado por utilizadores diferentes para o mesmo período, garantindo que as reservas confirmadas respeitam a disponibilidade real. | **Implementado.** Restrição na própria base de dados, com testes de pedidos em simultâneo. |
| **Planeamento automático com IA** | O utilizador seleciona vários serviços e o sistema procura, através de um Problema de Satisfação de Restrições (CSP), uma combinação de recursos e horários que respeite as restrições existentes, recorrendo a backtracking, forward checking e à heurística MRV. | **Protótipo.** O CSP já funciona no serviço de scheduling, ainda fora do fluxo de reservas. |
| **Explicação de falhas e sugestão de alternativas** | Quando não existe combinação válida, o sistema indica o que impede a reserva e sugere alternativas, como outro horário ou recurso, em vez de uma simples recusa. | **3.ª entrega.** O protótipo já indica quando não há solução, mas ainda não explica porquê. |
| **Fila de espera** | Quando um recurso está ocupado, o utilizador pode entrar numa fila de espera. Se uma reserva for cancelada, a vaga é oferecida ao primeiro da fila, que tem 15 minutos para a aceitar. | **Implementado.** A vaga é oferecida por ordem de chegada, com 15 minutos para aceitar. |
| **Notificações por email** | O utilizador recebe um email quando faz uma reserva, quando cancela uma reserva, quando entra na fila de espera e quando abre uma vaga na fila de espera. | **Parcial.** Os pedidos de email já ficam guardados na base de dados; o envio fica para a 3.ª entrega. |
| **Funcionalidades do administrador** | O administrador gere utilizadores, categorias, recursos e reservas, e dispõe de um painel administrativo (dashboard) com uma visão geral da plataforma. | **Implementado.** Gestão de categorias, recursos, reservas e utilizadores, e painel de administração. |
| **Histórico de reservas** | O utilizador consulta as suas reservas anteriores e acompanha a sua atividade na plataforma. | **Implementado.** Reservas futuras e passadas. |

**Requisitos não funcionais**

| Característica | Descrição | Estado (2.ª entrega) |
|---|---|---|
| **Arquitetura orientada a serviços** | O sistema é composto por vários microsserviços, entre os quais um serviço dedicado ao CSP. Os serviços são empacotados em contentores Docker e orquestrados com Kubernetes. | **Parcial.** Auth, booking e scheduling em Docker Compose. Kubernetes na 3.ª entrega. |
| **Segurança da plataforma** | Comunicação protegida por HTTPS, autenticação com 2FA e registo de auditoria (logs) das ações relevantes. | **Parcial.** 2FA, Argon2, AES-GCM e JWT. HTTPS e registo de auditoria na 3.ª entrega. |
| **Consistência e concorrência** | As reservas são confirmadas através de transações na base de dados, garantindo consistência perante pedidos em simultâneo. | **Implementado.** Transações e restrições na base de dados. |
| **Replicação dos dados** | A base de dados é replicada para evitar que uma falha isolada comprometa o funcionamento do sistema. | **3.ª entrega.** Os serviços já correm em dois servidores. A replicação da base de dados fica para a 3.ª entrega. |
| **Tolerância a falhas** | O sistema deteta falhas nos serviços e recupera automaticamente, mantendo-se disponível. A tolerância a falhas é demonstrada através de testes de falha. | **Parcial.** Failover do Nginx entre os dois servidores e healthchecks, demonstrados na apresentação. |
| **Monitorização e estado do sistema** | Visão geral do estado dos serviços e recursos, permitindo identificar situações que afetem o funcionamento normal. | **Parcial.** Healthchecks e logs do Nginx. Prometheus e Grafana na 3.ª entrega. |
| **Extensibilidade** | O núcleo de reservas genérico permite acrescentar novas categorias de serviço sem redesenhar o sistema. | **Implementado.** Categorias e recursos genéricos, criados pela API. |

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

- **Plataforma única para serviços heterogéneos:** o núcleo de reservas genérico e extensível permite tratar coworking, estacionamento e desporto com as mesmas regras, e novas categorias e recursos já podem ser criados pela API sem alterar o núcleo.
- **Planeamento conjunto de reservas interdependentes:** já existe um protótipo de CSP, com backtracking, forward checking e a heurística MRV, que prepara o planeamento de várias reservas em conjunto. A integração no fluxo de reservas está prevista para a fase seguinte.
- **Explicação de falhas:** o protótipo já indica quando não há combinação válida. A explicação do motivo e a sugestão de alternativas estão previstas para a fase seguinte.
- **Consistência perante concorrência:** a base de dados impede reservas sobrepostas sobre o mesmo recurso, validado com testes de pedidos em simultâneo. O replaneamento automático acompanha a integração do CSP.
- **Arquitetura distribuída tolerante a falhas:** três microsserviços, com bases de dados próprias nos serviços de autenticação e de reservas, a correr em dois servidores com failover automático do Nginx. A migração para Kubernetes e a replicação da base de dados completam esta arquitetura na fase seguinte.

## 6. Reflexão

### 6.1 Lições aprendidas

- **Definir e reduzir o âmbito cedo:** após a conversa com os docentes, o âmbito foi simplificado (o restaurante saiu e o ginásio e a quadra de padel passaram a formar uma só categoria), o que tornou o projeto mais realista para o tempo disponível.
- **Ter uma arquitetura de referência única:** a divisão em serviços foi revista até ficar alinhada com o diagrama de distribuição apresentado (por exemplo, o catálogo passou a ser um módulo do Booking). Desde então, qualquer alteração que o afete é comunicada e confirmada antes de ser feita.
- **Decidir em grupo as questões em aberto:** assuntos com impacto transversal, como as notificações por email e a migração para Alembic, foram resolvidos em reunião, evitando decisões isoladas.
- **Entregar primeiro um sistema distribuído a funcionar:** adiar o Kubernetes e a replicação da base de dados para a 3.ª entrega permitiu demonstrar já nesta fase o failover entre dois servidores.
- **Integrar cedo o trabalho em paralelo:** o backend e as migrações com Alembic foram desenvolvidos em branches separadas, e a fusão exigiu ajustes (nomes de bases de dados, rotas e scripts de inicialização).
- **Testar o arranque completo em várias máquinas:** problemas como permissões nos scripts de inicialização da base de dados só apareceram ao arrancar o ambiente noutra máquina, o que mostrou a importância de documentar e testar o arranque.

### 6.2 Limitações

- A solução encontra-se em desenvolvimento, pelo que nem todas as funcionalidades descritas estão implementadas.
- O CSP ainda não está integrado no fluxo de reservas e não explica o motivo quando não há solução.
- O Kubernetes, o HTTPS, a replicação da base de dados e a monitorização com Prometheus e Grafana ainda não estão implementados.
- As notificações por email ainda não são enviadas (os pedidos ficam guardados), e a alteração de reservas, o bloqueio por tentativas e a recuperação de palavra-passe ainda não existem.
- As páginas de categoria e de recurso da interface ainda usam dados fictícios, e a disponibilidade conjunta do profissional e do espaço nas aulas de personal trainer ainda não é considerada.
- Nesta fase, as reservas usam um intervalo livre (início e fim escolhidos pelo utilizador); horários dependentes de cada categoria ficam para uma evolução posterior.
- A plataforma é exclusivamente web, sem aplicação móvel.
- A gestão de permissões limita-se a dois papéis (administrador e utilizador), sem administradores por categoria.
- Não estão previstas reservas recorrentes nem check-in/check-out.

### 6.3 Trabalho futuro

Como trabalho futuro, prevê-se a migração para Kubernetes no Azure com HTTPS, a replicação do PostgreSQL com CloudNativePG, a integração do CSP no fluxo de reservas com a explicação de falhas e a otimização com branch and bound, o envio de emails, o bloqueio por tentativas e a recuperação de palavra-passe, a alteração de reservas, a conclusão do frontend, a monitorização com Prometheus e Grafana e os testes de falha e de carga. Numa fase posterior, poderão ainda ser exploradas as funcionalidades extra identificadas, como as preferências do utilizador, o código QR, a exportação de reservas, as estatísticas de utilização e o sistema de favoritos, bem como horários de reserva específicos para cada categoria.