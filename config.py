import os
import glob
import streamlit as st

DB_PATH = "fuphigimed.db"

AZUL_MARINHO_MASTER = "#163274"
AZUL_CIANO_HIGIMED = "#0089C4"
CIANO_VIBRANTE = "#00A8E8"
FUNDO_SUAVE = "#F3F7FB"

MODALIDADES_OFICIAIS = [
    "Carro Próprio",
    "Carro Técnica",
]

MODALIDADES_MAP = {
    "CARRO PROPRIO": "Carro Próprio",
    "CARRO PRÓPRIO": "Carro Próprio",
    "CARRO TECNICA": "Carro Técnica",
    "CARRO TÉCNICA": "Carro Técnica",
}

CORES_FAROL = {
    "🟢 NF na Mão & Baixada": "#10b981",
    "🟡 NF na Mão (Pendente Baixa ERP)": "#f59e0b",
    "🔵 Em Rota (Aguardando Retorno)": "#0089C4",
    "🟠 Sem Romaneio (Faturada)": "#fb923c",
}

def buscar_imagem_corporativa(nomes_exatos: list[str], palavras_chave: list[str]) -> str | None:
    pastas = [".", "assets"]
    for pasta in pastas:
        for nome in nomes_exatos:
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                return caminho
        for chave in palavras_chave:
            for ext in ["webp", "jpg", "jpeg", "png"]:
                encontrados = glob.glob(os.path.join(pasta, f"*{chave}*.{ext}"))
                if encontrados:
                    return encontrados[0]
    return None

def aplicar_estilo_higimed():
    st.markdown(
        f"""
        <style>
            [data-testid="stSidebar"], [data-testid="collapsedControl"] {{
                display: none !important;
            }}
            .stApp {{
                background: linear-gradient(180deg, #EBF3FA 0%, {FUNDO_SUAVE} 35%, #FFFFFF 100%);
            }}
            .block-container {{
                padding-top: 1.1rem;
                padding-bottom: 2.5rem;
                max-width: 1480px;
            }}
            .banner-institucional {{
                background: linear-gradient(135deg, #FFFFFF 0%, #F7FBFF 100%);
                border: 1px solid #D5E5F5;
                border-left: 6px solid {AZUL_MARINHO_MASTER};
                border-right: 6px solid {AZUL_CIANO_HIGIMED};
                border-radius: 18px;
                padding: 14px 24px;
                margin-bottom: 1.1rem;
                box-shadow: 0 8px 24px rgba(22, 50, 116, 0.07);
            }}
            .titulo-sistema {{
                background: linear-gradient(90deg, {AZUL_MARINHO_MASTER} 0%, {AZUL_CIANO_HIGIMED} 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 1.8rem;
                font-weight: 800;
                margin: 0;
                letter-spacing: -0.02em;
            }}
            .subtitulo-sistema {{
                color: #475569;
                font-size: 0.92rem;
                font-weight: 500;
                margin: 2px 0 0 0;
            }}
            .badge-transportadoras {{
                display: inline-block;
                margin-top: 8px;
                padding: 5px 14px;
                background: linear-gradient(90deg, #E0F2FE 0%, #EEF6FF 100%);
                color: {AZUL_MARINHO_MASTER};
                border: 1px solid #BAE6FD;
                border-radius: 999px;
                font-size: 0.78rem;
                font-weight: 700;
            }}
            [data-testid="stMetric"] {{
                background-color: #FFFFFF;
                border: 1px solid #DCE9F7;
                border-top: 4px solid {AZUL_CIANO_HIGIMED};
                border-radius: 14px;
                padding: 14px 18px;
                box-shadow: 0 4px 14px rgba(22, 50, 116, 0.05);
                transition: transform 0.15s ease;
            }}
            [data-testid="stMetric"]:hover {{
                transform: translateY(-2px);
            }}
            [data-testid="stMetricLabel"] {{
                font-size: 0.82rem;
                color: #334155;
                font-weight: 700;
            }}
            [data-testid="stMetricValue"] {{
                font-size: clamp(1.2rem, 1.55vw, 1.7rem) !important;
                color: {AZUL_MARINHO_MASTER};
                font-weight: 800;
                white-space: nowrap !important;
                overflow: visible !important;
                text-overflow: unset !important;
            }}
            .stTabs [data-baseweb="tab-list"] {{
                gap: 10px;
                background-color: #E2EEF9;
                padding: 6px;
                border-radius: 14px;
                border-bottom: none;
            }}
            .stTabs [data-baseweb="tab"] {{
                background-color: transparent;
                border: none;
                border-radius: 10px;
                padding: 9px 22px;
                font-weight: 700;
                color: {AZUL_MARINHO_MASTER};
            }}
            .stTabs [aria-selected="true"] {{
                background: linear-gradient(90deg, {AZUL_MARINHO_MASTER} 0%, {AZUL_CIANO_HIGIMED} 100%) !important;
                color: #FFFFFF !important;
                box-shadow: 0 4px 10px rgba(22, 50, 116, 0.2);
            }}
            div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {{
                background: linear-gradient(90deg, {AZUL_MARINHO_MASTER} 0%, {AZUL_CIANO_HIGIMED} 100%);
                border: none;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 10px;
                box-shadow: 0 3px 10px rgba(0, 137, 196, 0.25);
            }}
            div.stButton > button[kind="primary"]:hover, div.stFormSubmitButton > button[kind="primary"]:hover {{
                opacity: 0.92;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )