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
reservas; sistemas distribuídos; microsserviços; Problema de Satisfação de Restrições (CSP); autenticação de dois fatores (2FA); tolerância a falhas; failover; Docker; Kubernetes; Python

## 9. Tecnologias utilizadas
**Em utilização (2.ª entrega):** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, HTML, CSS, JavaScript, Nginx, Docker, Docker Compose, JWT, TOTP (pyotp), Argon2, AES-GCM, Pytest, GitHub, ClickUp

**Previstas (3.ª entrega):** Kubernetes, CloudNativePG, Ingress com HTTPS (TLS), SMTP (envio de emails), Prometheus, Grafana, K6

## 10. Resumo curto
O SlotUp é uma plataforma web distribuída de reservas para complexos empresariais, que reúne num único sistema a gestão de coworking, estacionamento e desporto (personal trainer e quadra de padel). Assenta num núcleo de reservas genérico e extensível, com fila de espera e dois perfis, administrador e utilizador, com acesso protegido por autenticação de dois fatores. Um componente de Inteligência Artificial, baseado num Problema de Satisfação de Restrições (CSP), planeia várias reservas interdependentes em simultâneo. Nesta fase existe um protótipo do CSP, ainda fora do fluxo de reservas. O sistema é composto por três microsserviços em Python, que correm em contentores Docker em dois servidores, com failover automático do Nginx. A migração para Kubernetes, a replicação da base de dados e o envio de notificações por email ficam para a fase seguinte.