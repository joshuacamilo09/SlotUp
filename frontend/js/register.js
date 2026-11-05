// ===== REGISTO: criar conta → configurar 2FA → entrar =====

// Já tem sessão? Não faz sentido registar outra conta.
if (Auth.getToken()) location.replace("index.html");

const registerForm = document.getElementById("register-form");
const setupForm = document.getElementById("setup-form");
const stepLabel = document.getElementById("step-label");

// Token temporário: só na memória da página (igual ao login)
let preToken = null;

// ----- Passo 1: dados da conta -----
registerForm.addEventListener("submit", (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página
  comBotao(document.getElementById("register-btn"), document.getElementById("register-alert"), async () => {
    const name = document.getElementById("nome").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    // 1) Cria a conta (201). Se o email já existir, o backend responde 409
    //    e o comBotao mostra "Este email já está registado".
    await api.register(name, email, password);

    // 2) Login automático com os mesmos dados: a conta é nova, por isso
    //    a resposta é sempre MFA_SETUP_REQUIRED.
    const res = await api.login(email, password);
    preToken = res.pre_auth_token;

    // 3) Mostra o QR code e passa para o passo 2
    await prepararSetup2fa(preToken);
    registerForm.classList.add("hidden");
    setupForm.classList.remove("hidden");
    stepLabel.textContent = "Passo 2 de 2";
    document.getElementById("code").focus();
  });
});

// ----- Passo 2: primeiro código, ativa o 2FA e entra -----
setupForm.addEventListener("submit", (e) => {
  e.preventDefault();
  comBotao(document.getElementById("setup-btn"), document.getElementById("setup-alert"), async () => {
    const res = await api.enable2fa(preToken, document.getElementById("code").value.trim());
    await concluirLogin(res);
  });
});