// ===== REDEFINIR A PALAVRA-PASSE (design do Dario) =====
// Fluxo do backend: o admin gera um código de uso único (Administração → Utilizadores)
// e entrega o link à pessoa; aqui ela escolhe a palavra-passe nova.
// Rota pública: POST /api/auth/password/reset { token, new_password } → 204

const $ = (seletor) => document.querySelector(seletor);
const MINIMO = 10;   // mesma regra do backend (schemas.py: min_length=10)

// As 3 "telas" desta página: só uma aparece de cada vez
const vistas = { nova: $("#vista-nova"), feito: $("#vista-feito"), invalido: $("#vista-invalido") };

function mostrar(nome) {
  for (const [chave, el] of Object.entries(vistas)) el.hidden = chave !== nome;
  vistas[nome].querySelector("h1").focus();   // leitores de ecrã anunciam a tela nova
}

// ===== O CÓDIGO =====
// Aceita o código sozinho ou o link inteiro que o admin copiou (tira o ?token=... do link)
function extrairCodigo(valor) {
  const texto = valor.trim();
  try {
    return new URL(texto).searchParams.get("token") ?? texto;   // é um link
  } catch {
    return texto;                                                // não é um link: é o próprio código
  }
}

// Veio pelo link do admin? Então o código já está no endereço e o campo fica escondido
let codigo = new URLSearchParams(location.search).get("token");
if (codigo) {
  $("#campo-codigo").hidden = true;
  $("#nova-texto").textContent = "Escolha uma palavra-passe nova para a sua conta.";
  // Tira o código do endereço: assim não fica no histórico do navegador
  history.replaceState(null, "", location.pathname);
}

// ===== REGRAS QUE FICAM VERDES ENQUANTO SE ESCREVE =====
function avaliarRegras() {
  const senha = $("#senha").value;
  const estado = {
    tamanho: senha.length >= MINIMO,
    igual: senha !== "" && senha === $("#senha2").value,
  };
  document.querySelectorAll(".regra").forEach((li) => {
    const ok = estado[li.dataset.regra];
    li.classList.toggle("ok", ok);
    li.querySelector(".icone").textContent = ok ? "check_circle" : "radio_button_unchecked";
  });
  return estado;
}

function mostrarErro(texto) {
  $("#nova-erro").textContent = texto;
  $("#nova-erro").hidden = false;
}

["#senha", "#senha2", "#codigo"].forEach((id) => $(id).addEventListener("input", () => {
  avaliarRegras();
  $("#nova-erro").hidden = true;
}));

// ===== GUARDAR =====
$("#form-nova").addEventListener("submit", async (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página

  const token = codigo || extrairCodigo($("#codigo").value);
  if (!token) {
    mostrarErro("Introduza o código que o administrador lhe deu.");
    $("#codigo").focus();
    return;
  }
  // O backend só aceita códigos com 20 a 128 caracteres: um código mais curto está incompleto
  if (token.length < 20) {
    mostrar("invalido");
    return;
  }
  const regras = avaliarRegras();
  if (!regras.tamanho) {
    mostrarErro(`A palavra-passe precisa de pelo menos ${MINIMO} caracteres.`);
    $("#senha").focus();
    return;
  }
  if (!regras.igual) {
    mostrarErro("As duas palavras-passe não coincidem.");
    $("#senha2").focus();
    return;
  }

  const botao = $("#guardar-botao");
  botao.disabled = true;
  botao.textContent = "A guardar…";
  try {
    await api.resetPassword(token, $("#senha").value);
    $("#senha").value = "";
    $("#senha2").value = "";
    mostrar("feito");
  } catch (err) {
    // 400 "Token inválido ou expirado": o código não serve (errado, usado ou expirado)
    if (err.status === 400) mostrar("invalido");
    else mostrarErro(err.message);
  } finally {
    botao.disabled = false;
    botao.textContent = "Guardar";
  }
});

// ===== CÓDIGO INVÁLIDO → TENTAR OUTRO =====
$("#outro-codigo").addEventListener("click", () => {
  codigo = null;                      // esquece o código do link
  $("#codigo").value = "";
  $("#campo-codigo").hidden = false;  // agora a pessoa escreve o código à mão
  $("#nova-texto").textContent = "Introduza o código que o administrador lhe deu e escolha uma palavra-passe nova.";
  mostrar("nova");
  $("#codigo").focus();
});

avaliarRegras();