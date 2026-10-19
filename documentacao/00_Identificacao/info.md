# SlotUp

## 1. Título do projeto
SlotUp: plataforma distribuída de reservas para complexos empresariais

## 2. Ano letivo
2026/2027

## 3. Semestre
5.º semestre

## 4. Curso(s) envolvido(s)
Licenciatura em Engenharia Informática

## 5. Unidade(s) curricular(es)
Projeto de Desenvolvimento de Software (com integração de Sistemas Distribuídos, Inteligência Artificial, Segurança e Engenharia de Software)

## 6. Docente(s)
- Miguel Boavida
- Pedro Rosa
- Rui Ramos
- Sérgio Nunes
- Samuel Gomes


## 7. Estudantes participantes
- Gabriel Rezende (20240343)
- Dário Bandanhe (20241751)
- Edmilson Tudo (20241542)
- Joshua Camilo (20240716)

Grupo 4 (turma D02)

## 8. Palavras-chave
reservas; sistemas distribuídos; microsserviços; Problema de Satisfação de Restrições (CSP); autenticação de dois fatores (2FA); tolerância a falhas; Docker; Kubernetes; Python

## 9. Tecnologias utilizadas
Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, CloudNativePG, HTML, CSS, JavaScript, Nginx, Docker, Docker Compose, Kubernetes, Ingress com HTTPS (TLS), JWT, TOTP (pyotp), Argon2, AES-GCM, SMTP, Prometheus, Grafana, Pytest, K6, GitHub, ClickUp

## 10. Resumo curto
O SlotUp é uma plataforma web distribuída de reservas para complexos empresariais, que reúne num único sistema a gestão de coworking, estacionamento e desporto (personal trainer e quadra de padel). Assenta num núcleo de reservas genérico e extensível, com fila de espera, notificações por email e dois perfis, administrador e utilizador, com acesso protegido por autenticação de dois fatores. Um componente de Inteligência Artificial, baseado num Problema de Satisfação de Restrições (CSP), planeia várias reservas interdependentes em simultâneo e, quando não há solução, explica o motivo e sugere alternativas. O sistema é composto por três microsserviços desenvolvidos em Python, empacotados em Docker e orquestrados com Kubernetes, com base de dados replicada e validação da tolerância a falhas através de testes de falha.