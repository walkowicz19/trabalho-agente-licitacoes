/**
 * app.js — Lógica do dashboard Agente de Licitações TechBridge Brasil
 *
 * Responsabilidades:
 * - Enviar busca para a API (POST /api/buscar)
 * - Escutar progresso via SSE (GET /api/progresso)
 * - Controlar as etapas do pipeline de análise
 * - Renderizar cards de licitações com Tailwind CSS e Lucide Icons
 * - Abrir e fechar drawer de análise completa
 * - Disparar exportação CSV e PDF
 * - Gerenciar histórico de buscas
 */

"use strict";

// ── Estado da aplicação ────────────────────────────────────────────────────

const estado = {
  resultados: [],          // Lista de licitações analisadas
  palavraChaveAtiva: "",   // Palavra-chave atual
  buscaEmAndamento: false, // Bloqueio de buscas simultâneas
};

// ── Referências do DOM ─────────────────────────────────────────────────────

const formBusca          = document.getElementById("form-busca");
const btnBuscar          = document.getElementById("btn-buscar");
const btnLimpar          = document.getElementById("btn-limpar");
const sliderScore        = document.getElementById("slider-score");
const labelSlider        = document.getElementById("label-slider");
const gradeCards         = document.getElementById("grade-cards");
const contadorResultados = document.getElementById("contador-resultados");
const listaHistorico     = document.getElementById("lista-historico");
const messageBar         = document.getElementById("message-bar");
const fluxoMensagem      = document.getElementById("fluxo-mensagem");
const header             = document.getElementById("header");
const btnExportarCsv     = document.getElementById("btn-exportar-csv");
const btnExportarPdf     = document.getElementById("btn-exportar-pdf");

// Drawer
const drawerOverlay      = document.getElementById("drawer-overlay");
const drawer             = document.getElementById("drawer");
const btnFecharDrawer    = document.getElementById("btn-fechar-drawer");

// ── Inicialização ─────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  carregarHistorico();
  carregarResultados();
  configurarEventos();
  atualizarIconesLucide();
});

function atualizarIconesLucide() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function configurarEventos() {
  // Busca e filtros
  formBusca.addEventListener("submit", aoEnviarBusca);
  btnLimpar.addEventListener("click", limparFormulario);

  // Slider de score mínimo (filtro client-side imediato)
  sliderScore.addEventListener("input", () => {
    labelSlider.textContent = sliderScore.value;
    filtrarCardsPorScore(Number(sliderScore.value));
  });

  // Header com sombra suave ao rolar a página principal
  const mainEl = document.getElementById("main");
  mainEl.addEventListener("scroll", () => {
    header.classList.toggle("com-sombra", mainEl.scrollTop > 4);
  });

  // Exportações
  btnExportarCsv.addEventListener("click", () => baixarArquivo("/api/exportar/csv", "licitacoes-techbridge.csv"));
  btnExportarPdf.addEventListener("click", () => baixarArquivo("/api/exportar/pdf", "relatorio-licitacoes.pdf"));

  // Fechamento do Drawer
  btnFecharDrawer.addEventListener("click", fecharDrawer);
  drawerOverlay.addEventListener("click", fecharDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") fecharDrawer();
  });

  // Exportar PDF a partir do Drawer
  document.getElementById("drawer-btn-exportar-pdf").addEventListener("click", () => {
    baixarArquivo("/api/exportar/pdf", "relatorio-licitacoes.pdf");
  });

  // Limpar Histórico de Buscas
  const btnLimparHist = document.getElementById("btn-limpar-historico");
  if (btnLimparHist) {
    btnLimparHist.addEventListener("click", async () => {
      try {
        await fetch("/api/historico", { method: "DELETE" });
        await carregarHistorico();
        mostrarMensagem("Histórico de buscas limpo com sucesso.", "sucesso");
      } catch (erro) {
        mostrarMensagem(`Erro ao limpar histórico: ${erro.message}`, "erro");
      }
    });
  }
}


// ── Busca de Licitações ───────────────────────────────────────────────────

async function aoEnviarBusca(evento) {
  evento.preventDefault();

  if (estado.buscaEmAndamento) return;

  const palavraChave = document.getElementById("campo-palavra-chave").value.trim();
  if (!palavraChave) {
    mostrarMensagem("Digite uma palavra-chave para buscar oportunidades.", "erro");
    return;
  }

  const valorMin = document.getElementById("campo-valor-min").value || null;
  const valorMax = document.getElementById("campo-valor-max").value || null;

  const params = new URLSearchParams({ palavra_chave: palavraChave });
  if (valorMin) params.append("valor_minimo", valorMin);
  if (valorMax) params.append("valor_maximo", valorMax);

  iniciarEstadoDeBusca(palavraChave);

  try {
    // Inicia a busca assíncrona no backend
    await fetch(`/api/buscar?${params}`, { method: "POST" });

    // Conecta ao fluxo de eventos SSE
    escutarProgressoSSE(palavraChave);

  } catch (erro) {
    finalizarEstadoDeBusca();
    mostrarMensagem(`Erro ao conectar com o servidor: ${erro.message}`, "erro");
  }
}

function iniciarEstadoDeBusca(palavraChave) {
  estado.buscaEmAndamento = true;
  estado.palavraChaveAtiva = palavraChave;
  btnBuscar.disabled = true;
  btnBuscar.innerHTML = `
    <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>
    <span>Processando...</span>
  `;
  atualizarIconesLucide();

  esconderMensagem();
  resetarDiagramaFluxo();
  renderizarSkeletons();
}

function finalizarEstadoDeBusca() {
  estado.buscaEmAndamento = false;
  btnBuscar.disabled = false;
  btnBuscar.innerHTML = `
    <i data-lucide="search" class="w-4 h-4"></i>
    <span>Buscar Oportunidades</span>
  `;
  atualizarIconesLucide();
}

// ── SSE (Server-Sent Events) — Progresso do Agente ─────────────────────────

function escutarProgressoSSE(palavraChave) {
  const url = `/api/progresso?palavra_chave=${encodeURIComponent(palavraChave)}`;
  const fonte = new EventSource(url);

  fonte.onmessage = (evento) => {
    const dados = JSON.parse(evento.data);
    processarEventoProgresso(dados, fonte);
  };

  fonte.onerror = () => {
    fonte.close();
    finalizarEstadoDeBusca();
  };
}

async function processarEventoProgresso(dados, fonteSSE) {
  const { etapa, status, mensagem, total } = dados;

  if (mensagem) {
    atualizarMensagemFluxo(mensagem);
  }

  if (etapa && etapa > 0) {
    atualizarNoFluxo(etapa, status);
  }

  // Etapa final concluída
  if (etapa === 5 && status === "concluido") {
    fonteSSE.close();
    finalizarEstadoDeBusca();
    await carregarResultados();
    await carregarHistorico();

    if (estado.resultados.length > 0) {
      btnExportarCsv.disabled = false;
      btnExportarPdf.disabled = false;
      mostrarMensagem(`Análise concluída com sucesso. ${total || estado.resultados.length} oportunidades identificadas.`, "sucesso");
    } else {
      mostrarMensagem("Nenhuma licitação com fit comercial encontrada para os termos informados.", "erro");
    }
  }
}

// ── Pipeline de Análise (Diagrama de Fluxo) ───────────────────────────────

function resetarDiagramaFluxo() {
  for (let i = 1; i <= 5; i++) {
    const no = document.getElementById(`no-${i}`);
    if (no) {
      no.classList.remove("ativo", "concluido");
      const statusEl = no.querySelector(".fluxo-no-status");
      if (statusEl) statusEl.textContent = "Aguardando";
    }

    if (i < 5) {
      const seta = document.getElementById(`seta-${i}-${i + 1}`);
      if (seta) seta.classList.remove("ativa", "concluida");
    }
  }
  fluxoMensagem.textContent = "Iniciando rastreamento de editais...";
}

function atualizarNoFluxo(numeroEtapa, status) {
  const no = document.getElementById(`no-${numeroEtapa}`);
  if (!no) return;

  no.classList.remove("ativo", "concluido");
  const statusEl = no.querySelector(".fluxo-no-status");

  if (status === "ativo") {
    no.classList.add("ativo");
    if (statusEl) statusEl.textContent = "Executando";

    if (numeroEtapa > 1) {
      const seta = document.getElementById(`seta-${numeroEtapa - 1}-${numeroEtapa}`);
      if (seta) seta.classList.add("ativa");
    }
  }

  if (status === "concluido") {
    no.classList.add("concluido");
    if (statusEl) statusEl.textContent = "Concluído";

    if (numeroEtapa > 1) {
      const seta = document.getElementById(`seta-${numeroEtapa - 1}-${numeroEtapa}`);
      if (seta) {
        seta.classList.remove("ativa");
        seta.classList.add("concluida");
      }
    }
  }
}

function atualizarMensagemFluxo(mensagem) {
  fluxoMensagem.textContent = mensagem;
}

// ── Resultados e Renderização de Cards ────────────────────────────────────

async function carregarResultados() {
  try {
    const scoreMinimo = Number(sliderScore.value);
    const resposta = await fetch(`/api/resultados?score_minimo=${scoreMinimo}`);
    const dados = await resposta.json();
    estado.resultados = dados.resultados || [];
    renderizarCards(estado.resultados);

    if (estado.resultados.length > 0) {
      btnExportarCsv.disabled = false;
      btnExportarPdf.disabled = false;
    }
  } catch (erro) {
    mostrarMensagem(`Erro ao carregar resultados: ${erro.message}`, "erro");
  }
}

function renderizarCards(lista) {
  gradeCards.innerHTML = "";

  if (lista.length === 0) {
    gradeCards.innerHTML = `
      <div id="estado-vazio" class="col-span-full py-16 px-4 text-center flex flex-col items-center justify-center bg-white border border-dashed border-slate-200 rounded-xl shadow-xs">
        <div class="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 mb-3 border border-slate-200/80">
          <i data-lucide="search-x" class="w-6 h-6"></i>
        </div>
        <h3 class="text-sm font-semibold text-slate-800 mb-1">Nenhum resultado encontrado</h3>
        <p class="text-xs text-slate-500 max-w-sm leading-relaxed">
          Tente buscar com palavras-chave mais amplas ou reduza o filtro de score mínimo na barra lateral.
        </p>
      </div>
    `;
    contadorResultados.classList.add("hidden");
    atualizarIconesLucide();
    return;
  }

  contadorResultados.textContent = `${lista.length} ${lista.length === 1 ? "oportunidade" : "oportunidades"}`;
  contadorResultados.classList.remove("hidden");

  lista.forEach((item, indice) => {
    const card = criarCardHtml(item, indice);
    gradeCards.appendChild(card);
  });

  atualizarIconesLucide();
}

function criarCardHtml(item, indice) {
  const { licitacao, analise } = item;
  const score = analise.score;
  const { classeScore, labelAdequacao } = calcularClasseScore(score);

  const valorFmt = (licitacao.valor_estimado !== null && licitacao.valor_estimado !== undefined)
    ? `R$ ${licitacao.valor_estimado.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "Consulte o edital";

  let dataLabel = "Encerramento";
  let dataFmt = "Consulte o edital";
  if (licitacao.data_encerramento) {
    dataLabel = "Encerramento";
    dataFmt = formatarData(licitacao.data_encerramento);
  } else if (licitacao.data_publicacao) {
    dataLabel = "Publicação";
    dataFmt = `Publ: ${formatarData(licitacao.data_publicacao)}`;
  }

  const card = document.createElement("article");
  card.className = "bg-white rounded-xl border border-slate-200/80 p-5 shadow-card hover:shadow-card-hover hover:border-slate-300 transition-all duration-200 flex flex-col justify-between gap-3 cursor-pointer group card-licitacao focus:outline-none focus:ring-2 focus:ring-sky-500/20";
  card.setAttribute("role", "listitem");
  card.setAttribute("tabindex", "0");
  card.setAttribute("aria-label", `Licitação: ${licitacao.objeto}`);
  card.style.animationDelay = `${indice * 40}ms`;

  card.innerHTML = `
    <div class="space-y-3">
      <!-- Topo: Badge de Fit e Score Numérico -->
      <div class="flex items-center justify-between gap-2">
        <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wide badge-${classeScore}">
          <i data-lucide="${classeScore === 'alta' ? 'sparkles' : classeScore === 'media' ? 'check' : 'alert-circle'}" class="w-3 h-3"></i>
          <span>${labelAdequacao}</span>
        </span>
        <div class="flex items-baseline gap-1">
          <span class="text-xl font-bold tracking-tight score-${classeScore}">${score}</span>
          <span class="text-[10px] text-slate-400 font-medium">/100</span>
        </div>
      </div>

      <!-- Barra Linear de Score -->
      <div class="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden" role="progressbar" aria-valuenow="${score}" aria-valuemin="0" aria-valuemax="100">
        <div class="h-full rounded-full barra-${classeScore} transition-all duration-500" style="width: ${score}%"></div>
      </div>

      <!-- Órgão Licitante -->
      <div class="flex items-center gap-1.5 text-slate-500 text-[11px] font-medium pt-1">
        <i data-lucide="building-2" class="w-3.5 h-3.5 text-slate-400 flex-shrink-0"></i>
        <span class="truncate font-semibold uppercase tracking-wider">${escaparHtml(licitacao.orgao_nome)}</span>
      </div>

      <!-- Objeto da Licitação -->
      <h3 class="text-sm font-semibold text-slate-900 line-clamp-2 leading-snug group-hover:text-sky-600 transition-colors">
        ${escaparHtml(licitacao.objeto)}
      </h3>
    </div>

    <div class="space-y-3 pt-2 border-t border-slate-100">
      <!-- Metadados: Valor e Prazo -->
      <div class="grid grid-cols-2 gap-2 text-xs text-slate-600">
        <div class="flex items-center gap-1.5 truncate" title="Valor Estimado">
          <i data-lucide="banknote" class="w-3.5 h-3.5 text-slate-400 flex-shrink-0"></i>
          <span class="truncate font-medium text-slate-800">${valorFmt}</span>
        </div>
        <div class="flex items-center gap-1.5 truncate" title="${dataLabel}">
          <i data-lucide="calendar" class="w-3.5 h-3.5 text-slate-400 flex-shrink-0"></i>
          <span class="truncate">${dataFmt}</span>
        </div>
      </div>

      <!-- Botão de Ação -->
      <div class="flex items-center justify-between text-xs font-medium text-sky-700 pt-1 group-hover:text-sky-800">
        <span>Ver análise completa</span>
        <i data-lucide="arrow-right" class="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform"></i>
      </div>
    </div>
  `;

  const abrirHandler = () => abrirDrawer(item);
  card.addEventListener("click", abrirHandler);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      abrirHandler();
    }
  });

  return card;
}

// ── Filtragem Local por Score ─────────────────────────────────────────────

function filtrarCardsPorScore(scoreMinimo) {
  const filtrados = estado.resultados.filter(r => r.analise.score >= scoreMinimo);
  renderizarCards(filtrados);
}

// ── Skeleton Loader ───────────────────────────────────────────────────────

function renderizarSkeletons() {
  gradeCards.innerHTML = "";
  contadorResultados.classList.add("hidden");

  for (let i = 0; i < 6; i++) {
    const sk = document.createElement("div");
    sk.className = "bg-white rounded-xl border border-slate-200/80 p-5 shadow-card space-y-4";
    sk.setAttribute("aria-hidden", "true");
    sk.innerHTML = `
      <div class="flex justify-between items-center">
        <div class="w-24 h-5 rounded-md skeleton-shimmer"></div>
        <div class="w-10 h-6 rounded-md skeleton-shimmer"></div>
      </div>
      <div class="w-full h-1.5 rounded-full skeleton-shimmer"></div>
      <div class="w-2/3 h-3 rounded skeleton-shimmer"></div>
      <div class="w-full h-10 rounded skeleton-shimmer"></div>
      <div class="pt-3 border-t border-slate-100 flex justify-between">
        <div class="w-24 h-4 rounded skeleton-shimmer"></div>
        <div class="w-20 h-4 rounded skeleton-shimmer"></div>
      </div>
    `;
    gradeCards.appendChild(sk);
  }
}

// ── Drawer de Análise Completa ────────────────────────────────────────────

function abrirDrawer(item) {
  const { licitacao, analise } = item;
  const score = analise.score;
  const { classeScore, labelAdequacao } = calcularClasseScore(score);

  document.getElementById("drawer-orgao").textContent = licitacao.orgao_nome;
  document.getElementById("drawer-titulo").textContent = licitacao.objeto;

  const scoreNumEl = document.getElementById("drawer-score-numero");
  scoreNumEl.textContent = `${score}/100`;
  scoreNumEl.className = `text-2xl font-bold tracking-tight score-${classeScore}`;

  const scoreBarraEl = document.getElementById("drawer-score-barra");
  scoreBarraEl.style.width = `${score}%`;
  scoreBarraEl.className = `h-full rounded-full barra-${classeScore} transition-all duration-500`;

  document.getElementById("drawer-justificativa").textContent = analise.justificativa_score || "Análise realizada conforme aderência ao portfólio corporativo.";
  document.getElementById("drawer-resumo").textContent = analise.resumo || "Não disponível.";
  document.getElementById("drawer-pitch").textContent = analise.pitch || "Não disponível.";

  document.getElementById("drawer-badge-container").innerHTML = `
    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold badge-${classeScore}">
      <i data-lucide="${classeScore === 'alta' ? 'sparkles' : classeScore === 'media' ? 'check' : 'alert-circle'}" class="w-3.5 h-3.5"></i>
      <span>${labelAdequacao}</span>
    </span>
  `;

  // Pontos Fortes
  const listaPF = document.getElementById("drawer-pontos-fortes");
  listaPF.innerHTML = (analise.pontos_fortes || []).map(p => `
    <li class="flex items-start gap-2 bg-emerald-50/40 p-2.5 rounded-lg border border-emerald-100 text-slate-700">
      <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5"></i>
      <span class="leading-relaxed">${escaparHtml(p)}</span>
    </li>
  `).join("") || `<li class="text-slate-400 italic">Nenhum ponto forte registrado.</li>`;

  // Riscos
  const listaR = document.getElementById("drawer-riscos");
  listaR.innerHTML = (analise.riscos || []).map(r => `
    <li class="flex items-start gap-2 bg-rose-50/40 p-2.5 rounded-lg border border-rose-100 text-slate-700">
      <i data-lucide="alert-triangle" class="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5"></i>
      <span class="leading-relaxed">${escaparHtml(r)}</span>
    </li>
  `).join("") || `<li class="text-slate-400 italic">Nenhum risco relevante identificado.</li>`;

  // Metadados Técnicos
  const valorFmt = (licitacao.valor_estimado !== null && licitacao.valor_estimado !== undefined)
    ? `R$ ${licitacao.valor_estimado.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "Consulte o edital";

  const dataLabel = licitacao.data_encerramento
    ? "Data de Encerramento"
    : (licitacao.data_publicacao ? "Data de Publicação" : "Prazo");

  const dataFmt = licitacao.data_encerramento
    ? formatarData(licitacao.data_encerramento)
    : (licitacao.data_publicacao ? formatarData(licitacao.data_publicacao) : "Consulte o edital");

  document.getElementById("drawer-meta").innerHTML = `
    <div>
      <span class="text-slate-400 block text-[10px] uppercase font-medium tracking-wider">Valor Estimado</span>
      <span class="font-semibold text-slate-800">${valorFmt}</span>
    </div>
    <div>
      <span class="text-slate-400 block text-[10px] uppercase font-medium tracking-wider">${dataLabel}</span>
      <span class="font-medium text-slate-800">${dataFmt}</span>
    </div>
    <div>
      <span class="text-slate-400 block text-[10px] uppercase font-medium tracking-wider">Modalidade</span>
      <span class="font-medium text-slate-800 truncate block">${licitacao.modalidade || "Não informado"}</span>
    </div>
    <div>
      <span class="text-slate-400 block text-[10px] uppercase font-medium tracking-wider">UASG / Órgão</span>
      <span class="font-medium text-slate-800 font-mono">${licitacao.uasg || "Não informado"}</span>
    </div>
  `;

  // Link do Edital
  const linkEdital = document.getElementById("drawer-link-edital");
  if (licitacao.link_edital) {
    linkEdital.href = licitacao.link_edital;
    linkEdital.style.display = "inline-flex";
  } else {
    linkEdital.style.display = "none";
  }

  // Exibição do Drawer
  drawerOverlay.classList.remove("hidden");
  drawerOverlay.classList.add("visivel");
  drawerOverlay.setAttribute("aria-hidden", "false");

  drawer.classList.remove("translate-x-full");
  drawer.classList.add("visivel");
  drawer.setAttribute("aria-hidden", "false");

  btnFecharDrawer.focus();
  document.body.style.overflow = "hidden";

  atualizarIconesLucide();
}

function fecharDrawer() {
  drawerOverlay.classList.add("hidden");
  drawerOverlay.classList.remove("visivel");
  drawerOverlay.setAttribute("aria-hidden", "true");

  drawer.classList.add("translate-x-full");
  drawer.classList.remove("visivel");
  drawer.setAttribute("aria-hidden", "true");

  document.body.style.overflow = "";
}

// ── Histórico de Buscas ───────────────────────────────────────────────────

async function carregarHistorico() {
  try {
    const resposta = await fetch("/api/historico");
    const dados = await resposta.json();
    const historico = dados.historico || [];

    if (historico.length === 0) {
      listaHistorico.innerHTML = `<li class="text-slate-400 py-1 italic">Nenhuma busca recente.</li>`;
      return;
    }

    listaHistorico.innerHTML = historico
      .slice(0, 6)
      .map(item => `
        <li class="historico-item flex items-center justify-between p-2 rounded-lg cursor-pointer hover:bg-slate-100/70 text-slate-700 transition-colors group"
            tabindex="0" role="button"
            aria-label="Repetir busca: ${escaparHtml(item.palavra_chave)}"
            data-palavra="${escaparHtml(item.palavra_chave)}">
          <div class="flex items-center gap-2 truncate">
            <i data-lucide="clock" class="w-3 h-3 text-slate-400 group-hover:text-sky-600 transition-colors flex-shrink-0"></i>
            <span class="truncate font-medium">${escaparHtml(item.palavra_chave)}</span>
          </div>
          <span class="text-[10px] text-slate-400 flex-shrink-0 ml-2">${formatarDataRelativa(item.criado_em)}</span>
        </li>
      `).join("");

    listaHistorico.querySelectorAll(".historico-item").forEach(item => {
      item.addEventListener("click", () => {
        document.getElementById("campo-palavra-chave").value = item.dataset.palavra;
        document.getElementById("campo-palavra-chave").focus();
      });
    });

    atualizarIconesLucide();

  } catch {
    // Falha silenciosa para histórico
  }
}

// ── Exportação ────────────────────────────────────────────────────────────

async function baixarArquivo(url, nomeArquivo) {
  try {
    const resposta = await fetch(url);
    if (!resposta.ok) {
      mostrarMensagem("Não há resultados para exportar.", "erro");
      return;
    }
    const blob = await resposta.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.setAttribute("download", nomeArquivo);
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
    }, 2000);
  } catch (erro) {
    mostrarMensagem(`Erro ao exportar arquivo: ${erro.message}`, "erro");
  }
}

// ── Notificações (Message Bar) ────────────────────────────────────────────

function mostrarMensagem(texto, tipo) {
  const icone = tipo === "erro" ? "alert-circle" : "check-circle-2";
  messageBar.innerHTML = `
    <i data-lucide="${icone}" class="w-4 h-4 flex-shrink-0"></i>
    <span>${escaparHtml(texto)}</span>
  `;
  messageBar.className = tipo === "erro" ? "erro" : "sucesso";
  messageBar.classList.remove("hidden");
  atualizarIconesLucide();
}

function esconderMensagem() {
  messageBar.className = "hidden";
  messageBar.innerHTML = "";
}

// ── Limpar Formulário ─────────────────────────────────────────────────────

function limparFormulario() {
  formBusca.reset();
  sliderScore.value = 0;
  labelSlider.textContent = "0";
  esconderMensagem();
}

// ── Utilitários ───────────────────────────────────────────────────────────

function calcularClasseScore(score) {
  if (score >= 70) return { classeScore: "alta",  labelAdequacao: "Alta Adequação" };
  if (score >= 40) return { classeScore: "media", labelAdequacao: "Adequação Média" };
  return               { classeScore: "baixa", labelAdequacao: "Baixa Adequação" };
}

function formatarData(dataIso) {
  if (!dataIso) return null;
  try {
    return new Date(dataIso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return dataIso; }
}

function formatarDataRelativa(dataIso) {
  if (!dataIso) return "";
  try {
    const diferenca = Date.now() - new Date(dataIso).getTime();
    const horas = Math.floor(diferenca / 3_600_000);
    if (horas < 1)  return "agora";
    if (horas < 24) return `há ${horas}h`;
    const dias = Math.floor(horas / 24);
    if (dias === 1) return "ontem";
    return `há ${dias}d`;
  } catch { return ""; }
}

function escaparHtml(texto) {
  if (!texto) return "";
  return String(texto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
