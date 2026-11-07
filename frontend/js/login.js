// ===== LOGIN: email + palavra-passe → 2FA (verificar ou configurar) =====

// Já tem sessão? Vai direto para a home.
if (Auth.getToken()) location.replace("index.html");

// Os três formulários da página (só um aparece de cada vez)
const forms = {
  login: document.getElementById("login-form"),
  code:  document.getElementById("code-form"),
  setup: document.getElementById("setup-form"),
};

// Token temporário do passo 1. Fica só na memória da página, não no localStorage:
// se a página recarregar, o utilizador volta ao passo 1 (mais seguro).
let preToken = null;

// Mostra um formulário e esconde os outros
function mostrar(nome) {
  for (const [chave, form] of Object.entries(forms)) {
    form.classList.toggle("hidden", chave !== nome);   // toggle(classe, condição)
  }
}

// Desativa o botão enquanto espera a resposta (evita clique duplo) e mostra os erros
async function comBotao(btn, alerta, acao) {
  hideAlert(alerta);
  btn.disabled = true;
  try {
    await acao();
  } catch (err) {
    showAlert(alerta, err.message);   // ex.: "Código inválido", "Demasiadas tentativas..."
  } finally {
    btn.disabled = false;
  }
}

// ----- Passo 1: email e palavra-passe -----
forms.login.addEventListener("submit", (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página
  comBotao(document.getElementById("login-btn"), document.getElementById("login-alert"), async () => {
    const res = await api.login(
      document.getElementById("email").value.trim(),
      document.getElementById("password").value
    );
    preToken = res.pre_auth_token;

    if (res.status === "MFA_REQUIRED") {
      // 2FA já ativo: só pede o código
      mostrar("code");
      document.getElementById("code").focus();
    } else {
      // MFA_SETUP_REQUIRED: primeiro acesso, gera o segredo e mostra o QR
      await prepararSetup2fa(preToken);
      mostrar("setup");
      document.getElementById("setup-code").focus();
    }
  });
});

// ----- Passo 2a: código de quem já tem 2FA -----
forms.code.addEventListener("submit", (e) => {
  e.preventDefault();
  comBotao(document.getElementById("code-btn"), document.getElementById("code-alert"), async () => {
    const res = await api.verify2fa(preToken, document.getElementById("code").value.trim());
    await concluirLogin(res);
  });
});

// ----- Passo 2b: primeiro código, ativa o 2FA -----
forms.setup.addEventListener("submit", (e) => {
  e.preventDefault();
  comBotao(document.getElementById("setup-btn"), document.getElementById("setup-alert"), async () => {
    const res = await api.enable2fa(preToken, document.getElementById("setup-code").value.trim());
    await concluirLogin(res);
  });
});

// ----- Voltar ao passo 1 (descarta o token temporário) -----
document.querySelectorAll(".back-link").forEach((link) =>
  link.addEventListener("click", (e) => {
    e.preventDefault();
    preToken = null;
    mostrar("login");
  })
);

// ----- "Esqueceu-se?": mostra/esconde o aviso "Contacte o administrador" -----
// Não há recuperação por email: o admin gera um código e o utilizador usa-o em reset.html
document.getElementById("forgot-link").addEventListener("click", (e) => {
  e.preventDefault();
  const ajuda = document.getElementById("forgot-help");
  const aberto = ajuda.classList.toggle("hidden") === false;   // toggle devolve true se ficou escondido
  e.currentTarget.setAttribute("aria-expanded", String(aberto));
});