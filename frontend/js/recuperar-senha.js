/* =====================================================================
   SlotUp · Recuperar palavra-passe
   Uma só página com 5 ecrãs (pedir, enviado, nova, feito, inválido).
   Só as 3 funções da secção 1 falam com o backend.
   ===================================================================== */
"use strict";

(() => {
  /* ===== 1. LIGAÇÃO AO BACKEND (o colega substitui só estas funções) =====
     Por agora fingem que correu bem, para a página funcionar sozinha.

     pedirLink(email)
       Pede o email com o link. Não deve revelar se o email existe.
       Rejeitar com Error("mensagem") se falhar.

     validarLink(token)
       O token vem do link do email (?token=...).
       Devolve { email } se for válido; rejeita se expirou/foi usado/não existe.

     redefinirSenha(token, senha)
       Grava a nova palavra-passe. Se o link já não for válido, rejeitar com
       um erro com codigo = "LINK_INVALIDO" (a página mostra o ecrã de link
       inválido). Qualquer outro erro mostra-se por baixo do formulário.     */
  async function pedirLink(email) {
    await esperar(500);
  }

  async function validarLink(token) {
    await esperar(300);
    if (token === "expirado") throw new Error("Link inválido");
    return { email: "nome@empresa.pt" };
  }

  async function redefinirSenha(token, senha) {
    await esperar(500);
  }

  /* ===== 2. Utilitários ===== */
  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const emailValido = (t) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t);
  const tempo = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  function avisar(texto, erro = false) {
    const t = document.createElement("div");
    t.className = "toast" + (erro ? " error" : "");
    t.textContent = texto;
    document.body.append(t);
    setTimeout(() => t.remove(), 3500);
  }
  function mostrarErro(el, texto) {
    el.textContent = texto;
    el.hidden = false;
  }
  function esconderErro(el) {
    el.hidden = true;
    el.textContent = "";
  }

  /* ===== 3. Elementos e estado ===== */
  const ESPERA_REENVIO = 60; // segundos até poder pedir outro link
  const vistas = {
    pedir: $("#vista-pedir"),
    enviado: $("#vista-enviado"),
    nova: $("#vista-nova"),
    feito: $("#vista-feito"),
    invalido: $("#vista-invalido"),
  };
  const emailEl = $("#email");
  const emailErroEl = $("#email-erro");
  const pedirBtn = $("#pedir-botao");
  const reenviarBtn = $("#reenviar");
  const reenviarTxt = $("#reenviar-txt");
  const senhaEl = $("#senha");
  const senha2El = $("#senha2");
  const novaErroEl = $("#nova-erro");
  const guardarBtn = $("#guardar-botao");

  let email = "";
  let token = null;
  let contagem = null;

  /* ===== 4. Trocar de ecrã ===== */
  function mostrar(nome) {
    Object.entries(vistas).forEach(([n, el]) => { el.hidden = n !== nome; });
    if (nome !== "enviado") clearInterval(contagem);
    $("h1", vistas[nome]).focus();
  }

  /* ===== 5. Ecrã 1: pedir o link ===== */
  $("#form-pedir").addEventListener("submit", async (e) => {
    e.preventDefault();
    const valor = emailEl.value.trim();
    esconderErro(emailErroEl);
    emailEl.removeAttribute("aria-invalid");

    if (!emailValido(valor)) {
      emailEl.setAttribute("aria-invalid", "true");
      mostrarErro(emailErroEl, "Indique um email válido.");
      emailEl.focus();
      return;
    }

    pedirBtn.disabled = true;
    pedirBtn.textContent = "A enviar…";
    try {
      await pedirLink(valor);
      email = valor;
      $("#enviado-email").textContent = email;
      mostrar("enviado");
      iniciarContagem();
    } catch (erro) {
      mostrarErro(emailErroEl, erro.message || "Não foi possível enviar o link. Tente outra vez.");
    } finally {
      pedirBtn.disabled = false;
      pedirBtn.textContent = "Enviar link";
    }
  });

  emailEl.addEventListener("input", () => {
    esconderErro(emailErroEl);
    emailEl.removeAttribute("aria-invalid");
  });

  /* ===== 6. Ecrã 2: enviado + contagem para reenviar ===== */
  function iniciarContagem() {
    clearInterval(contagem);
    let restante = ESPERA_REENVIO;
    reenviarBtn.disabled = true;
    reenviarTxt.textContent = `Reenviar em ${tempo(restante)}`;
    contagem = setInterval(() => {
      restante -= 1;
      if (restante <= 0) {
        clearInterval(contagem);
        reenviarBtn.disabled = false;
        reenviarTxt.textContent = "Reenviar link";
      } else {
        reenviarTxt.textContent = `Reenviar em ${tempo(restante)}`;
      }
    }, 1000);
  }

  reenviarBtn.addEventListener("click", async () => {
    reenviarBtn.disabled = true;
    reenviarTxt.textContent = "A enviar…";
    try {
      await pedirLink(email);
      avisar("Enviámos um novo link.");
      iniciarContagem();
    } catch (erro) {
      avisar(erro.message || "Não foi possível reenviar o link.", true);
      reenviarBtn.disabled = false;
      reenviarTxt.textContent = "Reenviar link";
    }
  });

  // Só para o protótipo: simulam o clique no link do email
  $("#proto-link").addEventListener("click", () => {
    token = "demo";
    abrirNova(email);
  });
  $("#proto-expirado").addEventListener("click", () => mostrar("invalido"));

  /* ===== 7. Ecrã 3: nova palavra-passe ===== */
  function abrirNova(emailDaConta) {
    $("#nova-email").textContent = emailDaConta;
    senhaEl.value = "";
    senha2El.value = "";
    esconderErro(novaErroEl);
    avaliarRegras();
    mostrar("nova");
  }

  function avaliarRegras() {
    const estado = {
      tamanho: senhaEl.value.length >= 8,
      numero: /\d/.test(senhaEl.value),
      igual: senhaEl.value !== "" && senhaEl.value === senha2El.value,
    };
    document.querySelectorAll(".regra").forEach((li) => {
      const ok = estado[li.dataset.regra];
      li.classList.toggle("ok", ok);
      $(".icone", li).textContent = ok ? "check_circle" : "radio_button_unchecked";
    });
    return estado;
  }

  [senhaEl, senha2El].forEach((el) => el.addEventListener("input", () => {
    avaliarRegras();
    esconderErro(novaErroEl);
  }));

  $("#form-nova").addEventListener("submit", async (e) => {
    e.preventDefault();
    const estado = avaliarRegras();
    if (!estado.tamanho || !estado.numero) {
      mostrarErro(novaErroEl, "A palavra-passe precisa de pelo menos 8 caracteres e de um número.");
      senhaEl.focus();
      return;
    }
    if (!estado.igual) {
      mostrarErro(novaErroEl, "As duas palavras-passe não coincidem.");
      senha2El.focus();
      return;
    }

    guardarBtn.disabled = true;
    guardarBtn.textContent = "A guardar…";
    try {
      await redefinirSenha(token, senhaEl.value);
      senhaEl.value = "";
      senha2El.value = "";
      mostrar("feito");
    } catch (erro) {
      if (erro.codigo === "LINK_INVALIDO") mostrar("invalido");
      else mostrarErro(novaErroEl, erro.message || "Não foi possível guardar a palavra-passe.");
    } finally {
      guardarBtn.disabled = false;
      guardarBtn.textContent = "Guardar";
    }
  });

  /* ===== 8. Ecrã 5: link inválido ===== */
  $("#novo-link").addEventListener("click", () => {
    token = null;
    mostrar("pedir");
    emailEl.value = email;
    emailEl.focus();
  });

  /* ===== 9. Arranque: se vier com ?token=..., abre direto a nova palavra-passe ===== */
  (async function arrancar() {
    token = new URLSearchParams(location.search).get("token");
    if (!token) return;
    try {
      const resposta = await validarLink(token);
      email = resposta.email;
      abrirNova(email);
    } catch {
      mostrar("invalido");
    }
  })();
})();