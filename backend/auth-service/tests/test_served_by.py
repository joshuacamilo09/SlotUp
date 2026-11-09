"""O cabeçalho X-Served-By identifica a réplica que atendeu o pedido (servidor 1 ou 2)."""
from app.config import get_settings


def test_resposta_normal_traz_x_served_by(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["X-Served-By"] == get_settings().instance_name


def test_resposta_de_erro_tambem_traz_x_served_by(client):
    # Rota que não existe: mesmo num 404 o cabeçalho tem de estar lá,
    # porque o middleware corre em todos os pedidos
    response = client.get("/rota-que-nao-existe")
    assert response.status_code == 404
    assert response.headers["X-Served-By"] == get_settings().instance_name