FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependências primeiro: a camada fica em cache enquanto o requirements.txt não mudar
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Não corre como root
RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
