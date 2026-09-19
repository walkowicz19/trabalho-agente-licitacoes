"""
Exportação de licitações analisadas para CSV e PDF.
Usa apenas bibliotecas open-source: csv (stdlib) e reportlab (gratuito).
"""

import csv
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER


def gerar_csv(licitacoes_analisadas: list[dict]) -> bytes:
    """
    Gera um arquivo CSV com todas as licitações analisadas.
    Retorna os bytes do arquivo para download.
    """
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", quoting=csv.QUOTE_ALL)

    # Cabeçalho
    escritor.writerow([
        "Score", "Adequação", "Órgão", "Objeto",
        "Valor Estimado (R$)", "Encerramento", "Modalidade",
        "UASG", "Resumo IA", "Pontos Fortes", "Riscos", "Pitch",
        "Analisada em", "Link Edital",
    ])

    for item in licitacoes_analisadas:
        licitacao = item["licitacao"]
        analise = item["analise"]

        score = analise["score"]
        adequacao = _label_adequacao(score)

        escritor.writerow([
            score,
            adequacao,
            licitacao.get("orgao_nome", ""),
            licitacao.get("objeto", ""),
            licitacao.get("valor_estimado", ""),
            licitacao.get("data_encerramento", ""),
            licitacao.get("modalidade", ""),
            licitacao.get("uasg", ""),
            analise.get("resumo", ""),
            " | ".join(analise.get("pontos_fortes", [])),
            " | ".join(analise.get("riscos", [])),
            analise.get("pitch", ""),
            item.get("analisada_em", ""),
            licitacao.get("link_edital", ""),
        ])

    # Retorna como bytes com BOM para compatibilidade com Excel
    return ("\ufeff" + saida.getvalue()).encode("utf-8")


def gerar_pdf(licitacoes_analisadas: list[dict], nome_empresa: str) -> bytes:
    """
    Gera um relatório PDF com as licitações analisadas.
    Retorna os bytes do arquivo para download.
    """
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    estilos = getSampleStyleSheet()
    cor_azul = colors.HexColor("#0078d4")

    estilo_titulo = ParagraphStyle(
        "titulo",
        parent=estilos["Heading1"],
        fontSize=18,
        textColor=cor_azul,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo",
        parent=estilos["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#616161"),
        spaceAfter=20,
    )
    estilo_secao = ParagraphStyle(
        "secao",
        parent=estilos["Heading2"],
        fontSize=12,
        textColor=cor_azul,
        spaceBefore=12,
        spaceAfter=4,
    )
    estilo_corpo = ParagraphStyle(
        "corpo",
        parent=estilos["Normal"],
        fontSize=9,
        leading=14,
    )

    elementos = []

    # Cabeçalho do relatório
    elementos.append(Paragraph(f"Relatório de Licitações — {nome_empresa}", estilo_titulo))
    data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")
    elementos.append(Paragraph(
        f"Gerado em {data_geracao} · {len(licitacoes_analisadas)} licitações analisadas",
        estilo_subtitulo,
    ))

    for item in licitacoes_analisadas:
        licitacao = item["licitacao"]
        analise = item["analise"]
        score = analise["score"]

        cor_score = _cor_score(score)
        adequacao = _label_adequacao(score)

        # Título da licitação
        elementos.append(Paragraph(
            f"<b>{licitacao.get('orgao_nome', 'Órgão não informado')}</b> — Score: {score}/100 ({adequacao})",
            estilo_secao,
        ))
        elementos.append(Paragraph(licitacao.get("objeto", ""), estilo_corpo))
        elementos.append(Spacer(1, 4))

        # Tabela de metadados
        valor = licitacao.get("valor_estimado")
        valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor else "Não informado"

        dados_tabela = [
            ["Valor Estimado", valor_fmt],
            ["Encerramento", licitacao.get("data_encerramento", "Não informado")],
            ["Modalidade", licitacao.get("modalidade", "")],
            ["UASG", licitacao.get("uasg", "Não informado")],
        ]

        tabela = Table(dados_tabela, colWidths=[4 * cm, 13 * cm])
        tabela.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#424242")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ]))
        elementos.append(tabela)
        elementos.append(Spacer(1, 6))

        # Análise de IA
        elementos.append(Paragraph(f"<b>Resumo:</b> {analise.get('resumo', '')}", estilo_corpo))
        pontos = " · ".join(analise.get("pontos_fortes", []))
        elementos.append(Paragraph(f"<b>Pontos fortes:</b> {pontos}", estilo_corpo))
        riscos = " · ".join(analise.get("riscos", []))
        elementos.append(Paragraph(f"<b>Riscos:</b> {riscos}", estilo_corpo))
        elementos.append(Paragraph(f"<b>Pitch:</b> {analise.get('pitch', '')}", estilo_corpo))
        elementos.append(Spacer(1, 16))

    documento.build(elementos)
    return buffer.getvalue()


def _label_adequacao(score: int) -> str:
    """Retorna o rótulo de adequação baseado no score."""
    if score >= 70:
        return "Alta Adequação"
    elif score >= 40:
        return "Adequação Média"
    return "Baixa Adequação"


def _cor_score(score: int) -> str:
    """Retorna o código hexadecimal de cor para o score."""
    if score >= 70:
        return "#57a300"
    elif score >= 40:
        return "#f7b900"
    return "#d13438"
