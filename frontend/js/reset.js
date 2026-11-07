// ===== REDEFINIR PALAVRA-PASSE com o código que o administrador entregou =====
//
// O admin gera o código no auth (POST /api/auth/users/{id}/password/reset) e dá-o
// em mão ao utilizador. Aqui o utilizador escreve o código e a palavra-passe nova.

const form   = document.getElementById("reset-form");
const alerta = document.getElementById("reset-alert");
const campoToken = document.getElementById("token");

// O código também pode vir num link: reset.html#token=...
// Vai depois do "#" (e não em "?token="): o browser nunca envia essa parte ao servidor,
// por isso o código não fica nos registos (logs) do Nginx.
const doLink = new URLSearchParams(location.hash.slice(1)).get("token");
if (doLink) {
  campoToken.value = doLink;
  history.replaceState(null, "", location.pathname);   // tira o código da barra de endereço
}

form.addEventListener("submit", (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página

  const token = campoToken.value.trim();
  const nova  = document.getElementById("password").value;
  const conf  = document.getElementById("password2").value;

  // Verificações rápidas antes de chamar a API (o backend volta a validar tudo)
  if (nova.length < 10) {
    showAlert(alerta, "A palavra-passe tem de ter pelo menos 10 caracteres.");
    return;
  }
  if (nova !== conf) {
    showAlert(alerta, "As palavras-passe não coincidem.");
    return;
  }

  comBotao(document.getElementById("reset-btn"), alerta, async () => {
    // Chamada direta ao request() do api.js, para não mexer no objeto api (é do Gabriel).
    // Resposta 204 (sem corpo) = alterada. Código errado, usado ou expirado = 400.
    await request("POST", "/auth/password/reset", { token, new_password: nova });
    form.classList.add("hidden");
    document.getElementById("reset-done").classList.remove("hidden");
  });
});