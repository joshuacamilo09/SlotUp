// ===== ALTERAR A PALAVRA-PASSE (com sessão iniciada) =====
// POST /api/auth/password/change { current_password, new_password } → { access_token } novo.
// O backend sobe a session_version: os tokens antigos deixam de valer no auth,
// por isso guardamos logo o token novo que vem na resposta.

const utilizador = requireAuth();   // sem sessão: vai para o login

const $ = (seletor) => document.querySelector(seletor);
const MINIMO = 10;   // mesma regra do registo (schemas.py: min_length=10)

// ===== REGRAS QUE FICAM VERDES ENQUANTO SE ESCREVE =====
function avaliarRegras() {
  const atual = $("#atual").value;
  const nova = $("#senha").value;
  const estado = {
    tamanho: nova.length >= MINIMO,
    diferente: nova !== "" && nova !== atual,   // o backend recusa a mesma (400)
    igual: nova !== "" && nova === $("#senha2").value,
  };
  document.querySelectorAll(".regra").forEach((li) => {
    const ok = estado[li.dataset.regra];
    li.classList.toggle("ok", ok);
    li.querySelector(".icone").textContent = ok ? "check_circle" : "radio_button_unchecked";
  });
  return estado;
}

function mostrarErro(texto, campo) {
  $("#erro").textContent = texto;
  $("#erro").hidden = false;
  if (campo) {
    campo.setAttribute("aria-invalid", "true");   // borda vermelha (regra do recuperar-senha.css)
    campo.focus();
  }
}

// Ao escrever: atualiza as regras e limpa o erro e as bordas vermelhas
["#atual", "#senha", "#senha2"].forEach((id) => $(id).addEventListener("input", () => {
  avaliarRegras();
  $("#erro").hidden = true;
  document.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
}));

// ===== GUARDAR =====
$("#form-alterar").addEventListener("submit", async (e) => {
  e.preventDefault();

  const regras = avaliarRegras();
  if (!$("#atual").value) return mostrarErro("Introduza a palavra-passe atual.", $("#atual"));
  if (!regras.tamanho) return mostrarErro(`A palavra-passe nova precisa de pelo menos ${MINIMO} caracteres.`, $("#senha"));
  if (!regras.diferente) return mostrarErro("A palavra-passe nova tem de ser diferente da atual.", $("#senha"));
  if (!regras.igual) return mostrarErro("As duas palavras-passe não coincidem.", $("#senha2"));

  const botao = $("#guardar-botao");
  botao.disabled = true;
  botao.textContent = "A guardar…";
  try {
    const res = await api.changePassword($("#atual").value, $("#senha").value);
    // Token novo: sem isto, o próximo pedido ao auth daria 401 e a sessão acabava
    Auth.setSession(res.access_token, utilizador);
    document.querySelectorAll("input").forEach((el) => (el.value = ""));
    $("#vista-form").hidden = true;
    $("#vista-feito").hidden = false;
    $("#vista-feito h1").focus();
  } catch (err) {
    // 401: palavra-passe atual errada (5 erros bloqueiam a conta → 429 com os minutos de espera)
    mostrarErro(err.message, err.status === 401 ? $("#atual") : null);
  } finally {
    botao.disabled = false;
    botao.textContent = "Guardar";
  }
});

avaliarRegras();