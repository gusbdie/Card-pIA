import io
import re
import json
import time
from typing import List
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
from PIL import Image
import pandas as pd
import numpy as np

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

app = FastAPI(title="cardapIA - Extrator Inteligente")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_DEFAULT = "AIzaSyA1A3acWTOUvF5mb65yrjxuCU1r8GxG6o0"

PROMPT_BASE = """
[Contexto] Você é a IA principal de um sistema de extração de cardápios. Leia o texto ou imagem fornecida e transforme em um objeto JSON com duas chaves estritas: "produtos" e "adicionais". 
A lista de produtos deve ter as chaves: cor, categoria, ativo, disponibilidade, tipo, produto, preco, descricao, adicional, codigo, imagem, pesavel, local_impressao.
A lista de adicionais deve ter as chaves: tipo, adicional, minimo, maximo, ativo, item, preco, descricao, codigo, imagem, local_impressao.

[Inteligência de Leitura]
O texto fornecido pode ter pontuações soltas. Limpe os nomes dos produtos.
1- Preços devem ser convertidos para float separando decimais por PONTO. Se não tiver preço, use 0.00.
2- Relacione os adicionais ao produto corretamente através da coluna "adicional".

[Observações Básicas]
1- A coluna 'cor' é 'Padrão', 'ativo' é 'Sim'.
2- A coluna 'adicional' na tabela produtos VINCULA o produto ao grupo de adicionais usando a mesma palavra-chave.
3- Em 'pesavel', aplique 'Sim' se for vendido no Kg, senão 'Não'.
4- 'local_impressao': Comidas = Cozinha 1, Bebidas = Copa.
5- Não invente produtos. Extraia tudo o que encontrar.
"""

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == '': return 0.0
        return float(str(val).replace(',', '.').strip())
    except:
        return 0.0

def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == '': return 0
        return int(float(str(val).replace(',', '.').strip()))
    except:
        return 0

def clean_string(val):
    if pd.isna(val): return ""
    return str(val).strip()

def parse_saipos_spreadsheet(file_bytes, ext):
    df = None
    if ext == 'csv':
        for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, header=None, sep=',', engine='python', on_bad_lines='skip')
                if len(df.columns) > 1: break
            except:
                pass
        
        if df is None or len(df.columns) <= 1:
            for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, header=None, sep=';', engine='python', on_bad_lines='skip')
                    if len(df.columns) > 1: break
                except:
                    pass
    else:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), header=None)
        except:
            pass
            
    if df is None or df.empty:
        return [], []
        
    header_idx = -1
    for i, row in df.iterrows():
        row_str = ' '.join([clean_string(x).upper() for x in row.values])
        if 'PRODUTO*' in row_str or 'ITEM*' in row_str or ('PRODUTO' in row_str and 'PREÇO' in row_str):
            header_idx = i
            break
            
    if header_idx == -1:
        return [], []
        
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx+1:].dropna(how='all')
    df.columns = [clean_string(c).upper().replace('*', '') for c in df.columns]
    df = df.replace({np.nan: ''})
    
    produtos = []
    adicionais = []
    
    if 'PRODUTO' in df.columns:
        for _, row in df.iterrows():
            nome_produto = clean_string(row.get('PRODUTO', ''))
            if not nome_produto: continue
            
            tipo_val = clean_string(row.get('TIPO', 'Comida'))
            if not tipo_val: tipo_val = "Comida"
                
            produtos.append({
                "cor": clean_string(row.get('COR', 'Padrão')) or 'Padrão',
                "categoria": clean_string(row.get('CATEGORIA', '')),
                "ativo": clean_string(row.get('ATIVO', 'Sim')) or 'Sim',
                "disponibilidade": clean_string(row.get('DISPONIBILIDADE', 'Delivery e Salão')) or 'Delivery e Salão',
                "tipo": tipo_val,
                "produto": nome_produto,
                "preco": safe_float(row.get('PREÇO', 0)),
                "descricao": clean_string(row.get('DESCRIÇÃO', '')),
                "adicional": clean_string(row.get('ADICIONAL', '')),
                "codigo": clean_string(row.get('CÓDIGO', '')),
                "imagem": clean_string(row.get('IMAGEM', '')),
                "pesavel": clean_string(row.get('PESÁVEL', 'Não')) or 'Não',
                "local_impressao": clean_string(row.get('LOCAL IMPRESSÃO', '')) or ("Cozinha 1" if tipo_val == "Comida" else "Copa")
            })
            
    elif 'ITEM' in df.columns:
        for _, row in df.iterrows():
            nome_item = clean_string(row.get('ITEM', ''))
            if not nome_item: continue
            
            adicionais.append({
                "tipo": clean_string(row.get('TIPO', 'Outro')) or 'Outro',
                "adicional": clean_string(row.get('ADICIONAL', '')),
                "minimo": safe_int(row.get('MÍNIMO', 0)),
                "maximo": safe_int(row.get('MÁXIMO', 1)),
                "ativo": clean_string(row.get('ATIVO', 'Sim')) or 'Sim',
                "item": nome_item,
                "preco": safe_float(row.get('PREÇO', 0)),
                "descricao": clean_string(row.get('DESCRIÇÃO', '')),
                "codigo": clean_string(row.get('CÓDIGO', '')),
                "imagem": clean_string(row.get('IMAGEM', '')),
                "local_impressao": clean_string(row.get('LOCAL IMPRESSÃO', '')) or "Cozinha 1"
            })
            
    return produtos, adicionais

def extrair_texto_automatico(texto: str) -> dict:
    produtos = []
    adicionais = []
    linhas = texto.split('\n')
    categoria_atual = "Geral"
    linha_anterior = ""

    for linha in linhas:
        linha = linha.strip()
        if not linha: continue

        if linha.lower().startswith("adicional:") or linha.lower().startswith("adicionais:"):
            if produtos:
                produto_pai = produtos[-1]["produto"]
                palavra_chave = f"Adicionais {produto_pai}"
                produtos[-1]["adicional"] = palavra_chave
                
                itens_str = re.split(r':', linha, maxsplit=1)[1]
                itens = [i.strip() for i in itens_str.split(',') if i.strip()]
                
                for item in itens:
                    adicionais.append({
                        "tipo": "Outro", "adicional": palavra_chave, "minimo": 0, "maximo": 1,
                        "ativo": "Sim", "item": item, "preco": 0.00, "descricao": "",
                        "codigo": "", "imagem": "", "local_impressao": produtos[-1]["local_impressao"]
                    })
            continue

        match_preco = re.search(r'(?:R\$)?\s*(\d{1,4}[.,]\d{2})', linha)

        if match_preco:
            preco_str = match_preco.group(1).replace(',', '.')
            preco = float(preco_str)
            nome = re.sub(r'(?:R\$)?\s*\d{1,4}[.,]\d{2}.*', '', linha).strip()
            nome = re.split(r'\||\-', nome)[0].strip()
            nome = re.sub(r'[\-\.]+$', '', nome).strip()

            if not nome and linha_anterior:
                nome = linha_anterior
                if produtos and produtos[-1]["descricao"].endswith(linha_anterior):
                    produtos[-1]["descricao"] = produtos[-1]["descricao"].replace(linha_anterior, "").strip()

            if nome:
                pesavel = "Sim" if "kg" in linha.lower() or "quilo" in linha.lower() else "Não"
                tipo = "Bebida" if any(x in nome.lower() for x in ['água', 'refrigerante', 'coca', 'suco', 'cerveja']) else "Comida"
                local_imp = "Copa" if tipo == "Bebida" else "Cozinha 1"

                produtos.append({
                    "cor": "Padrão", "categoria": categoria_atual, "ativo": "Sim", "disponibilidade": "Delivery e Salão",
                    "tipo": tipo, "produto": nome, "preco": preco, "descricao": "", "adicional": "",
                    "codigo": "", "imagem": "", "pesavel": pesavel, "local_impressao": local_imp
                })
        else:
            if len(linha) < 35 and not re.search(r'\d', linha):
                categoria_atual = linha.title()
            elif produtos:
                produtos[-1]["descricao"] = (produtos[-1]["descricao"] + " " + linha).strip() if produtos[-1]["descricao"] else linha
        
        linha_anterior = linha

    return {"produtos": produtos, "adicionais": adicionais}


@app.post("/api/extract")
async def extract_menu(
    texto: str = Form(None), 
    files: List[UploadFile] = File(None), 
    use_ai: str = Form("false"),
    pizza_flag: str = Form("false"),
    pizza_sabores: str = Form("1"),
    pizza_doces: str = Form("false"),
    variacoes_separadas: str = Form("false"),
    banco_imagens: str = Form(""),
    gemini_key: str = Form(None) # CHAVE DINÂMICA ENVIADA PELO FRONTEND
):
    usar_ia = use_ai.lower() == "true"
    
    if not texto and not files:
        raise HTTPException(status_code=400, detail="Envie um texto ou arquivos do cardápio.")
    
    texto_extraido = texto if texto else ""
    imagens_para_ia = []
    native_produtos = []
    native_adicionais = []

    try:
        if files:
            for file in files:
                if not file.filename: continue
                file_bytes = await file.read()
                ext = file.filename.split('.')[-1].lower()

                if ext == 'pdf':
                    try:
                        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                            for page in pdf.pages:
                                try:
                                    page_text = page.extract_text(layout=True)
                                except Exception:
                                    page_text = page.extract_text(layout=False)
                                
                                if page_text: 
                                    texto_extraido += page_text + "\n"
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Erro ao ler PDF: {str(e)}")
                
                elif ext in ['xls', 'xlsx', 'csv']:
                    try:
                        p, a = parse_saipos_spreadsheet(file_bytes, ext)
                        if p or a:
                            native_produtos.extend(p)
                            native_adicionais.extend(a)
                        else:
                            if ext == 'csv':
                                for enc in ['utf-8', 'latin1', 'cp1252']:
                                    try:
                                        df = pd.read_csv(io.BytesIO(file_bytes), header=None, encoding=enc, sep=None, engine='python')
                                        break
                                    except:
                                        pass
                            else:
                                df = pd.read_excel(io.BytesIO(file_bytes), header=None)
                            
                            df = df.dropna(how='all')
                            page_text = df.to_csv(index=False, header=False, sep=';')
                            if page_text:
                                texto_extraido += f"\n\n[INÍCIO PLANILHA: {file.filename}]\n" + page_text + f"\n[FIM PLANILHA: {file.filename}]\n"
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Erro ao ler Planilha Saipos: {str(e)}")

                elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                    if not usar_ia:
                        raise HTTPException(status_code=400, detail="Imagens requerem IA ativada.")
                    imagens_para_ia.append(Image.open(io.BytesIO(file_bytes)))

        if usar_ia and (texto_extraido or imagens_para_ia) and genai:
            
            # INICIALIZA A CHAVE SORTEADA PELO FRONT OU USA A PADRÃO
            chave_final = gemini_key.strip() if gemini_key and gemini_key.strip() else API_KEY_DEFAULT
            current_client = None
            try:
                current_client = genai.Client(api_key=chave_final)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Chave da API Gemini falhou: {str(e)}")

            prompt_dinamico = PROMPT_BASE
            if variacoes_separadas.lower() == "true": prompt_dinamico += "\n[VARIAÇÕES] Considere variações como PRODUTOS SEPARADOS."
            else: prompt_dinamico += "\n[VARIAÇÕES] Se tiver variações, deixe o preço zerado no produto e use adicionais."
            if pizza_flag.lower() == "true":
                prompt_dinamico += f"\n[PIZZA] Cardápio possui pizzas. Máximo sabores: {pizza_sabores}."
                if pizza_doces.lower() == "true": prompt_dinamico += " Separe salgadas e doces."
            
            if banco_imagens:
                prompt_dinamico += f"\n\n[MAPEAMENTO DE IMAGENS]\nNosso banco de dados já possui imagens vinculadas aos seguintes nomes: {banco_imagens}.\nSe você extrair um produto/adicional que seja sinônimo ou variação de algum item dessa lista, VOCÊ DEVE OBRIGATORIAMENTE nomear a chave 'produto' (ou 'item') com o NOME EXATO E IDENTICO que está na lista. Isso evitará duplicações."

            prompt_dinamico += f"\n\n[TEXTO BRUTO]\n{texto_extraido}\n\nRetorne APENAS o JSON válido, sem formatação extra."

            conteudos = [prompt_dinamico] + imagens_para_ia
            
            max_tentativas = 3
            resultado_estruturado = {"produtos": [], "adicionais": []}
            
            for tentativa in range(max_tentativas):
                try:
                    config_ia = types.GenerateContentConfig(temperature=0.1)
                    
                    response = current_client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=conteudos,
                        config=config_ia
                    )
                    res_text = response.text.replace('```json', '').replace('```', '').strip()
                    resultado_estruturado = json.loads(res_text)
                    break
                except Exception as erro_api:
                    if "503" in str(erro_api) and tentativa < max_tentativas - 1:
                        time.sleep(2)
                        continue
                    else:
                        raise erro_api

            resultado_estruturado["produtos"].extend(native_produtos)
            resultado_estruturado["adicionais"].extend(native_adicionais)

        else:
            if texto_extraido:
                resultado_estruturado = extrair_texto_automatico(texto_extraido)
            else:
                resultado_estruturado = {"produtos": [], "adicionais": []}
                
            resultado_estruturado["produtos"].extend(native_produtos)
            resultado_estruturado["adicionais"].extend(native_adicionais)

        return resultado_estruturado
    
    except Exception as e:
        print(f"Erro detalhado: {e}")
        raise HTTPException(status_code=500, detail=str(e))