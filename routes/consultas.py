from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session, g, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, and_
import os
import re
import requests
import time
import random
import asyncio
import queue
import sqlite3
import json

# Imports do Projeto
from models import Usuario, LogAuditoria, BuscaSemResultado, Veiculo
from decorators import admin_required, cadastro_required, edicao_required, exclusao_required
from utils import registrar_log, formatar_data, requer_modulo_ativo
from models import Veiculo, CachePlaca


# Define o Blueprint
consultas_bp = Blueprint('consultas', __name__)

# ------------------------------------------------------------------------------------
# ROTA PARA CARREGAR A PÁGINA DO FORMULÁRIO DE BUSCA (VELOCIDADE MÁXIMA)
# ------------------------------------------------------------------------------------
@consultas_bp.route('/buscar', methods=['GET'])
@login_required
@requer_modulo_ativo('consultas.buscar')
def buscar():
    """Apenas entrega o HTML bruto. ZERO consultas ao banco."""
    # A contagem de veículos foi movida para uma rota separada ou para o cache.
    return render_template('buscar.html', total_veiculos=None)


@consultas_bp.route('/api/total-veiculos', methods=['GET'])
@login_required
def api_total_veiculos():
    """Retorna apenas o número total de veículos para não travar a tela inicial."""
    try:
        total = g.db.query(func.count(Veiculo.id)).scalar()
        return jsonify({'total': total})
    except Exception:
        return jsonify({'total': 0}), 500


# ------------------------------------------------------------------------------------
# NOVA ROTA DE API
# ------------------------------------------------------------------------------------
@consultas_bp.route('/api/buscar-modelo', methods=['POST'])
@login_required
def api_buscar_modelo():
    """Processa a busca e retorna os dados (resultados ou sugestões) em JSON."""
    modelo = request.form.get('modelo', '').strip()
    ano = request.form.get('ano', default=None, type=int)
    cor = request.form.get('cor', '').strip().upper()

    cores_equivalentes = {
        'PRETO': ['PRETO', 'PRETA'], 'BRANCO': ['BRANCO', 'BRANCA'], 'VERMELHO': ['VERMELHO', 'VERMELHA'],
        'AMARELO': ['AMARELO', 'AMARELA'], 'CINZA': ['CINZA'], 'AZUL': ['AZUL'], 'VERDE': ['VERDE'],
        'MARROM': ['MARROM'], 'LARANJA': ['LARANJA'], 'ROSA': ['ROSA'], 'ROXO': ['ROXO', 'ROXA'],
        'PRATA': ['PRATA'], 'BEGE': ['BEGE'], 'OUTRA': ['OUTRA']
    }

    if modelo:
        modelo_upper = modelo.upper()
        modelo_tokens = modelo_upper.split()
        cor_detectada = None
        for token in list(modelo_tokens):
            for base_cor, variantes in cores_equivalentes.items():
                if token in variantes:
                    cor_detectada = base_cor
                    modelo_tokens.remove(token)
                    break
            if cor_detectada:
                break
        if not cor and cor_detectada:
            cor = cor_detectada
        modelo = ' '.join(modelo_tokens).strip()

    if not (modelo or ano or cor):
        return jsonify({'success': False, 'error': 'Pelo menos um filtro de busca é necessário.'}), 400

    query = g.db.query(Veiculo)
    detalhes_log = []

    if modelo:
        modelo_limpo = re.sub(r'[/.-]', ' ', modelo)
        palavras_chave = modelo_limpo.upper().split()
        condicoes = [Veiculo.modelo.ilike(f"%{palavra}%") for palavra in palavras_chave]
        if condicoes:
            query = query.filter(and_(*condicoes))
        detalhes_log.append(f"Modelo: {modelo}")

    if ano:
        query = query.filter(Veiculo.ano == ano)
        detalhes_log.append(f"Ano: {ano}")

    if cor and cor != 'TODAS':
        cores_consideradas = cores_equivalentes.get(cor.upper(), [cor.upper()])
        query = query.filter(Veiculo.cor.in_(cores_consideradas))
        detalhes_log.append(f"Cor: {cor}")

    resultados = query.all()
    sugestao = None
    cores_disponiveis = None

    if not resultados and modelo:
        try:
            termo_completo_para_log = modelo
            if cor:
                termo_completo_para_log = f"{modelo} {cor}"
            nova_busca_falha = BuscaSemResultado(
                termo_pesquisado=termo_completo_para_log,
                usuario_id=session['usuario_id']
            )
            g.db.add(nova_busca_falha)
            g.db.commit()
        except Exception as e:
            g.db.rollback()
            current_app.logger.error(f"Falha ao registrar busca sem resultado: {e}")
        
        if cor:
            modelo_limpo_sugestao = re.sub(r'[/.-]', ' ', modelo)
            palavras_chave_sugestao = modelo_limpo_sugestao.upper().split()
            condicoes_sugestao = [Veiculo.modelo.ilike(f"%{palavra}%") for palavra in palavras_chave_sugestao]
            veiculos_mesmo_modelo = []
            if condicoes_sugestao:
                veiculos_mesmo_modelo = g.db.query(Veiculo).filter(and_(*condicoes_sugestao)).all()
            if veiculos_mesmo_modelo:
                lista_de_cores = [v.cor for v in veiculos_mesmo_modelo if v.cor]
                if lista_de_cores:
                    cores_disponiveis = sorted(list(set(lista_de_cores)))
        
        if not cores_disponiveis:
            try:
                todos_modelos_tuplas = g.db.query(Veiculo.modelo).distinct().all()
                lista_de_modelos = [item[0] for item in todos_modelos_tuplas]
                if lista_de_modelos:
                    # Importação local para evitar erro se a lib não estiver instalada globalmente
                    from thefuzz import process as fuzzy_process
                    melhor_match = fuzzy_process.extractOne(modelo, lista_de_modelos)
                    if melhor_match and melhor_match[1] > 60:
                        sugestao = melhor_match[0]
            except Exception as e:
                current_app.logger.warning(f"Erro na sugestão fuzzy: {e}")

    # Log da busca
    log_final = f"Filtros: {', '.join(detalhes_log) if detalhes_log else 'Nenhum'}. Resultados: {len(resultados)}"
    registrar_log(usuario_id=session['usuario_id'], acao="Busca de veículo (API)", detalhes=log_final)

    resultados_dict = [veiculo.to_dict() for veiculo in resultados]

    return jsonify({
        'success': True,
        'resultados': resultados_dict,
        'modelo_pesquisado': modelo,
        'sugestao': sugestao,
        'cores_disponiveis': cores_disponiveis,
        'cor_pesquisada': cor,
        'permissoes': {
            'pode_editar': session.get('pode_editar', False),
            'pode_excluir': session.get('pode_excluir', False)
        }
    })

# ------------------------------------------------------
# ---  ROTA CHECKER99 MÓDULO -
# ------------------------------------------------------
@consultas_bp.route('/checker99')
@login_required
@requer_modulo_ativo('consultas.checker99_page')
def checker99_page():
    """Renderiza a página do módulo Checker CPF 99."""
    return render_template('checker99.html')

# ------------------------------------------------------
# PROXY PARA API DA 99 (VERSÃO MOBILE DEFINITIVA)
# ------------------------------------------------------
@consultas_bp.route('/proxy/99', methods=['POST'])
@login_required
def proxy_99():
    """
    Simula um dispositivo via Proxy com base na nova captura de tráfego.
    """
    cpf_raw = request.form.get('value')
    cpf = re.sub(r'[^0-9]', '', cpf_raw) if cpf_raw else ""

    if not cpf or len(cpf) != 11:
        return jsonify({'erro': 'CPF inválido'}), 400

    url_api_99 = 'https://mis.didiglobal.com/gulfstream/deadpool/register/checkIdNo'

    proxy99_secdd_authentication = os.getenv("PROXY99_SECDD_AUTHENTICATION")
    proxy99_wsgsig = os.getenv("PROXY99_WSGSIG")
    proxy99_uid = os.getenv("PROXY99_UID")
    proxy99_ticket = os.getenv("PROXY99_TICKET")

    missing_proxy99_env = [
        name for name, value in {
            "PROXY99_SECDD_AUTHENTICATION": proxy99_secdd_authentication,
            "PROXY99_WSGSIG": proxy99_wsgsig,
            "PROXY99_UID": proxy99_uid,
            "PROXY99_TICKET": proxy99_ticket,
        }.items() if not value
    ]

    if missing_proxy99_env:
        current_app.logger.error(f"Variáveis ausentes para proxy/99: {', '.join(missing_proxy99_env)}")
        return jsonify({'erro': 'Configuração incompleta do proxy/99.'}), 500

    # Headers atualizados conforme a captura do seu amigo
    headers = {
        'Host': 'mis.didiglobal.com',
        'Connection': 'keep-alive',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'Origin': 'https://page.99app.com',
        'Referer': 'https://page.99app.com/', # Adicionado barra no final conforme log
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/144.0.0.0',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'secdd-authentication': proxy99_secdd_authentication,
        'secdd-challenge': '4|1.5.14||||||',
        'wsgsig': proxy99_wsgsig
    }

    # Payload totalmente reestruturado
    data = {
        'a': '102930081',
        'activity_id': '102930081',
        'activity_type': '29',
        'channel': '28',
        'city_id': '55000071',
        'i': '4fQ8rpYl8ed2SzdHXlKGqQ==',
        'lang': 'pt-BR',
        'locale': 'pt_BR',
        'location_country': 'BR',
        'product_id': '16',
        'scene': '29',
        'shar_chanl': 'wa',
        'share_media': 'WHATSAPP',
        'uid': proxy99_uid,
        'url_id': '850665457',
        'url_type': '0',
        'ticket': proxy99_ticket,
        'identity': '3',
        'value': cpf, # CPF inserido aqui dinamicamente
        'end': 'WebEnd',
        'oid': '62df6bcd-80cf-4379-a143-e324a4f9a48f',
        'product': '2'
    }

    try:
        # Removido sleep excessivo para teste, mas mantendo um jitter mínimo
        time.sleep(random.uniform(0.2, 0.5))
        
        # Timeout aumentado levemente para garantir
        response = requests.post(url_api_99, headers=headers, data=data, timeout=20)
        
        # Log para debug (remova em produção se quiser)
        current_app.logger.info(f"[99MOBILE] Status: {response.status_code} | Body parcial: {response.text[:100]}")

        if response.status_code == 200:
            json_resp = response.json()
            errno = json_resp.get('errno')

            # Mantive a lógica de errno, mas valide se o json de resposta mantém essa estrutura
            if errno == 20006:
                return jsonify({'status': 'live', 'msg': 'Aprovado (Conta 99 Existente)', 'dados': json_resp})
            elif errno == 0:
                return jsonify({'status': 'die', 'msg': 'Reprovado (Sem cadastro)', 'dados': json_resp})
            
            # Caso o errno seja diferente, retorna o JSON puro para análise
            return jsonify(json_resp)
        
        return jsonify({'erro': f'Erro API: {response.status_code}', 'response': response.text}), response.status_code

    except Exception as e:
        current_app.logger.error(f"[99MOBILE] Erro Crítico: {e}")
        return jsonify({'erro': 'Erro interno.'}), 500

# ------------------------------------------------------
# ROTA PARA REGISTRAR LOG DE AUDITORIA DO CHECKER99
# ------------------------------------------------------
@consultas_bp.route('/log/checker99/start', methods=['POST'])
@login_required
@requer_modulo_ativo('/log/checker99/start')
def log_checker99_start():
    try:
        usuario = g.db.query(Usuario).filter_by(id=session['usuario_id']).first()
        if not usuario:
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        total_cpfs = request.form.get('total_cpfs', 0, type=int)
        if total_cpfs == 0:
            return jsonify({'erro': 'Nenhum CPF para registrar'}), 400

        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        detalhes = f"Iniciou verificação com {total_cpfs} CPFs. (IP: {ip_address})"

        registrar_log(usuario_id=usuario.id, acao="Verificação em Lote - Checker99", detalhes=detalhes)
        g.db.commit()
        return jsonify({'status': 'log registrado com sucesso'}), 200

    except Exception as e:
        g.db.rollback()
        current_app.logger.error(f"Falha ao registrar log para o Checker99: {e}")
        return jsonify({'erro': 'Falha interna ao registrar o log'}), 500
    

# ==========================================
# MÓDULO COMPARADOR FACIAL
# ==========================================

# URL da API de comparação
API_COMPARE_URL = os.getenv("API_COMPARE_URL")

@consultas_bp.route('/nova-comparacao')
@login_required
@requer_modulo_ativo('consultas.nova_comparacao')
def nova_comparacao():
    return render_template('custom_compare.html')

@consultas_bp.route('/api/iniciar-comparacao', methods=['POST'])
@login_required
def iniciar_comparacao():
    # --- 1. REGRA DE TEMPO (30s) ---
    current_time = time.time()
    last_time = session.get('last_compare_time')
    
    if last_time:
        elapsed = current_time - last_time
        if elapsed < 30:
            wait_time = int(30 - elapsed)
            return jsonify({'error': f'Aguarde {wait_time} segundos para uma nova comparação.'}), 429
    
    session['last_compare_time'] = current_time

    try:
        if not API_COMPARE_URL:
            return jsonify({'error': 'API_COMPARE_URL não configurada.'}), 500

        base = request.files.get('minha_imagem_base')
        lista_comparacao = request.files.getlist('minhas_imagens_comparar')

        if not base or not lista_comparacao:
            return jsonify({'error': 'Faltam arquivos.'}), 400

        # --- 2. REGRA DE QUANTIDADE (Segurança Máxima de 500 imagens) ---
        if len(lista_comparacao) > 500:
            return jsonify({'error': f'Limite de segurança excedido: {len(lista_comparacao)} imagens enviadas. Máximo permitido: 500.'}), 400

        files_to_send = []
        # Prepara a imagem base
        files_to_send.append(('base_file', (base.filename, base.read(), base.content_type)))
        
        # Prepara a lista de imagens para comparar
        for f in lista_comparacao:
            files_to_send.append(('compare_files[]', (f.filename, f.read(), f.content_type)))

        # Envia para a API externa
        resp = requests.post(API_COMPARE_URL, files=files_to_send, timeout=60)
        
        if resp.status_code != 200:
            return jsonify({'error': f'Erro na API Externa: {resp.status_code}'}), 500
            
        return jsonify(resp.json())

    except Exception as e:
        current_app.logger.error(f"Erro Iniciar Comparação Facial: {e}")
        return jsonify({'error': str(e)}), 500

@consultas_bp.route('/api/verificar-status/<task_id>', methods=['GET'])
@login_required
def verificar_status(task_id):
    try:
        if not API_COMPARE_URL:
            return jsonify({'error': 'API_COMPARE_URL não configurada.'}), 500

        resp = requests.get(f"{API_COMPARE_URL}?task_id={task_id}", timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        current_app.logger.error(f"Erro Status Comparação Facial: {e}")
        return jsonify({'error': str(e)}), 500
    


# ==========================================
# CAMADA DE BANCO DE DADOS (CACHE LOCAL)
# ==========================================
def init_db():
    """Cria a tabela de cache se não existir"""
    conn = sqlite3.connect('painel_arcangelo.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS placas_cache (
            placa TEXT PRIMARY KEY,
            json_resposta TEXT,
            data_consulta DATETIME
        )
    ''')
    conn.commit()
    conn.close()

def get_cache_placa(placa):
    """Verifica se a placa já existe no banco"""
    try:
        conn = sqlite3.connect('painel_arcangelo.db')
        cursor = conn.cursor()
        cursor.execute("SELECT json_resposta FROM placas_cache WHERE placa = ?", (placa,))
        result = cursor.fetchone()
        conn.close()
        if result:
            print(f"[Cache] Placa {placa} encontrada localmente!")
            return json.loads(result[0])
        return None
    except Exception as e:
        print(f"[Cache] Erro leitura: {e}")
        return None

def save_cache_placa(placa, dados_json):
    """Salva o resultado para consultas futuras"""
    try:
        conn = sqlite3.connect('painel_arcangelo.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO placas_cache (placa, json_resposta, data_consulta)
            VALUES (?, ?, ?)
        ''', (placa, json.dumps(dados_json), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        print(f"[Cache] Placa {placa} salva com sucesso.")
    except Exception as e:
        print(f"[Cache] Erro gravação: {e}")

# Inicializa o banco ao rodar o script
init_db()


# ==========================================
# LÓGICA DE PARSING (LIMPEZA DE DADOS)
# ==========================================
def clean_and_parse_plate_data(response_text):
    if not response_text: return None
    
    # Remove linhas inúteis
    lines = response_text.split('\n')
    cleaned_lines = [l for l in lines if not any(x in l for x in ['👤 Usuário:', '🤖 Bot:', '🕵️', 'CONSULTA DE PLACA', 'bloqueado'])]
    cleaned_text = '\n'.join(cleaned_lines)

    result = {}
    
    def extract_value(text, pattern):
        patterns = [
            fr'{pattern}:.*?`([^`]+)`',
            fr'{pattern}:\s*([^\n]+)',
            fr'•.*?{pattern}:\s*([^\n]+)'
        ]
        for p in patterns:
            match = re.search(p, text, re.IGNORECASE)
            if match: return match.group(1).strip().replace('`', '')
        return None

    secoes_map = {
        'dados_principais': ('DADOS PRINCIPAIS', 'CARACTERÍSTICAS'),
        'caracteristicas': ('CARACTERÍSTICAS DO VEÍCULO', 'PROPRIETÁRIO'),
        'proprietario': ('PROPRIETÁRIO / FATURAMENTO', 'RESTRIÇÕES'),
        'restricoes': ('RESTRIÇÕES / ALERTAS', 'IMPORTAÇÃO'),
        'datas': ('DATAS E SERVIÇOS', None)
    }

    for chave, (inicio, fim) in secoes_map.items():
        start_idx = cleaned_text.find(inicio)
        if start_idx != -1:
            end_idx = cleaned_text.find(fim) if fim and cleaned_text.find(fim) != -1 else len(cleaned_text)
            section_text = cleaned_text[start_idx:end_idx]
            
            dados = {}
            if chave == 'dados_principais':
                dados = {
                    'placa': extract_value(section_text, 'Placa'),
                    'chassi': extract_value(section_text, 'Chassi'),
                    'renavam': extract_value(section_text, 'RENAVAM'),
                    'situacao': extract_value(section_text, 'Situação'),
                    'municipio': extract_value(section_text, 'Município') or extract_value(section_text, 'Município Emplacamento'),
                    'uf': extract_value(section_text, 'UF') or extract_value(section_text, 'UF Emplacamento')
                }
            elif chave == 'caracteristicas':
                dados = {
                    'tipo_veiculo': extract_value(section_text, 'Tipo Veículo'),
                    'especie': extract_value(section_text, 'Espécie'),
                    'marca_modelo': extract_value(section_text, 'Marca / Modelo'),
                    'carroceria': extract_value(section_text, 'Tipo Carroceria'),
                    'cor': extract_value(section_text, 'Cor'),
                    'categoria': extract_value(section_text, 'Categoria'),
                    'ano_fab': extract_value(section_text, 'Ano Fabricação'),
                    'ano_mod': extract_value(section_text, 'Ano Modelo'),
                    'potencia': extract_value(section_text, 'Potência'),
                    'cilindradas': extract_value(section_text, 'Cilindradas'),
                    'combustivel': extract_value(section_text, 'Combustível'),
                    'motor': extract_value(section_text, 'Motor'),
                    'cambio': extract_value(section_text, 'Câmbio'),
                    'procedencia': extract_value(section_text, 'Procedência'),
                    'eixos': extract_value(section_text, 'Qtd. Eixos'),
                    'lotacao': extract_value(section_text, 'Lotação')
                }
            elif chave == 'proprietario':
                dados = {
                    'tipo_proprietario': extract_value(section_text, 'Tipo Proprietário'),
                    'cpf_cnpj': extract_value(section_text, 'CPF/CNPJ Proprietário') or extract_value(section_text, 'CPF/CNPJ'),
                    'nome': extract_value(section_text, 'Nome Proprietário'),
                    'tipo_doc_faturado': extract_value(section_text, 'Tipo Documento Faturado'),
                    'doc_faturado': extract_value(section_text, 'Documento Faturado'),
                    'uf_faturado': extract_value(section_text, 'UF Faturado')
                }
            elif chave == 'restricoes':
                dados = {
                    'restricao_1': extract_value(section_text, 'Restrição 1'),
                    'restricao_2': extract_value(section_text, 'Restrição 2'),
                    'restricao_3': extract_value(section_text, 'Restrição 3'),
                    'restricao_4': extract_value(section_text, 'Restrição 4'),
                    'multa_renainf': extract_value(section_text, 'Multa RENAINF'),
                    'restricao_renajud': extract_value(section_text, 'Restrição RENAJUD'),
                    'roubo_furto': extract_value(section_text, 'Roubo / Furto'),
                    'leilao': extract_value(section_text, 'Leilão'),
                    'comunicacao_venda': extract_value(section_text, 'Comunicação de Venda'),
                    'alarme': extract_value(section_text, 'Alarme')
                }
            elif chave == 'datas':
                dados = {
                    'dt_crv': extract_value(section_text, 'Data Emissão CRV'),
                    'dt_crlv': extract_value(section_text, 'Data Emissão CRLV'),
                    'licenciamento': extract_value(section_text, 'Ano Licenciamento Pago')
                }

            result[chave] = {k: v for k, v in dados.items() if v}

    return result


# ==========================================
# ROTAS FLASK - MÓDULO CONSULTA PLACA
# ==========================================

@consultas_bp.route('/buscar-placa')
@login_required
@requer_modulo_ativo('consultas.buscar_placa')
def buscar_placa():
    """Renderiza a página de consulta de placas."""
    return render_template('buscarplaca.html')


@consultas_bp.route('/api/consultar-placa', methods=['POST'])
@login_required
def api_consultar_placa():
    """
    API de Consulta de Placas (Refatorada v3 - Gonzales Nova API)
    - URL Atualizada: usa 'placa_serpro'.
    - Parser JSON: Adaptado para estrutura plana (sem aninhamento).
    - Datas: Tratamento para remover timestamp (T00:00:00).
    - Fallback: Sistema de Mock automático em caso de erro da API externa.
    """
    from datetime import datetime, timezone
    import requests
    
    # ==========================================================
    # CONFIGURAÇÕES & CONSTANTES
    # ==========================================================
    MODO_TESTE_FORCADO = False  # Defina True para não gastar créditos/simular
    API_KEY = os.getenv('GONZALES_API_KEY')
    
    # Helper para converter booleanos/strings em SIM/NÃO
    bool_to_text = lambda x: "SIM" if (x is True or str(x).upper() == 'TRUE') else "NÃO"

    # Helper para limpar datas com hora (ex: 2026-01-15T11:50:50 -> 2026-01-15)
    def limpar_data(d):
        if not d: return None
        if isinstance(d, str) and 'T' in d:
            return d.split('T')[0]
        return d

    # ==========================================================
    # 1. VALIDAÇÃO DE INPUT
    # ==========================================================
    data_input = request.get_json()
    placa = data_input.get('placa', '').upper().replace('-', '').strip()

    if not placa or len(placa) != 7:
        return jsonify({'error': 'Placa inválida.'}), 400

    # ==========================================================
    # 2. VERIFICAÇÃO DE CACHE (Prioridade Máxima)
    # ==========================================================
    try:
        cache = g.db.query(CachePlaca).filter_by(placa=placa).first()
        
        if cache:
            current_app.logger.info(f"⚡ [CACHE HIT] Placa {placa} retornada do banco.")
            registrar_log(current_user.id, 'CONSULTA PLACA (CACHE)', f'Placa: {placa}')
            return jsonify({
                'status': 'sucesso', 
                'origem': 'cache', 
                'data': cache.dados_json
            })
        
        current_app.logger.info(f"🌍 [CACHE MISS] Placa {placa} buscando na API externa...")

    except Exception as e:
        current_app.logger.error(f"⚠️ Erro ao ler cache (prosseguindo para API): {e}")

    # ==========================================================
    # 3. CONSULTA NA API EXTERNA
    # ==========================================================
    dados_api = None
    erro_api = None

    # Tenta buscar na API se NÃO for teste forçado e tiver chave
    if not MODO_TESTE_FORCADO and API_KEY:
        # ATUALIZAÇÃO: Parâmetro mudou de 'placa' para 'placa_serpro'
        url = f"https://consultasgonzales.com/apis/?apikey={API_KEY}&placa_serpro={placa}"

        try:
            # Timeout aumentado levemente para 20s
            response = requests.get(url, timeout=20)
            
            if response.status_code == 200:
                try:
                    dados_api = response.json()
                    
                    # Validação básica se o JSON tem conteúdo útil
                    # A nova API retorna 'codigoRenavam' ou 'placa'
                    if 'placa' not in dados_api and 'codigoRenavam' not in dados_api:
                         return jsonify({'error': 'Veículo não encontrado na base de dados.'}), 404
                         
                except requests.exceptions.JSONDecodeError:
                     # Captura casos onde API retorna 200 mas com corpo HTML (erro mascarado)
                     current_app.logger.error("❌ Erro: API retornou 200 mas o conteúdo não é JSON.")
                     erro_api = 'Erro de formato na resposta do provedor.'
            else:
                # Log limpo (sem HTML gigante)
                erro_msg = response.text[:200].replace('\n', ' ')
                current_app.logger.error(f"❌ Erro API Gonzales ({response.status_code}): {erro_msg}...")
                erro_api = 'Instabilidade no provedor de dados.'

        except requests.Timeout:
            erro_api = 'Tempo limite excedido na comunicação.'
        except Exception as e:
            current_app.logger.error(f"❌ Erro geral na requisição: {e}")
            erro_api = 'Erro interno na comunicação.'

    # ==========================================================
    # 4. MOCK / SIMULAÇÃO (Fallback se a API falhar)
    # ==========================================================
    usar_mock = MODO_TESTE_FORCADO or (dados_api is None and erro_api is not None)
    
    if usar_mock:
        # Se for erro real e não tivermos modo mock habilitado para produção, retorna o erro
        # Se quiser que sempre funcione (mesmo com dados falsos) quando a API cair, remova o 'if' abaixo
        if erro_api and not MODO_TESTE_FORCADO:
             return jsonify({'error': erro_api}), 502

        current_app.logger.warning(f"⚠️ ATIVANDO MOCK PARA PLACA {placa}")
        # Estrutura MOCK atualizada para o formato NOVO (plano)
        dados_api = {
            "placa": placa,
            "chassi": "9BWZZZ3VZHPMOCK99",
            "codigoRenavam": "12345678900",
            "descricaoMunicipioEmplacamento": "MOCK CITY",
            "ufJurisdicao": "SP",
            "situacao": "EM_CIRCULACAO",
            "descricaoMarcaModelo": "TOYOTA/COROLLA MOCK XEI",
            "anoFabricacao": 2025,
            "anoModelo": 2026,
            "descricaoCor": "PRATA",
            "descricaoCombustivel": "FLEX",
            "numeroMotor": "M20AFKS123",
            "potencia": "177",
            "cilindradas": "2000",
            "nomeProprietario": "USUARIO DE TESTE MOCK",
            "numeroIdentificacaoProprietario": "000.000.000-00",
            "descricaoRestricao1": "SEM RESTRICAO",
            "indicadorRouboFurto": False,
            "indicadorRestricaoRenajud": False,
            "indicadorMultaRenainf": False,
            "dataEmissaoCrv": "2025-01-01",
            "dataEmissaoCRLV": "2026-01-15T12:00:00",
            "anoExercicioLicenciamentoPago": "2026"
        }
        erro_api = None # Limpa erro para prosseguir

    # ==========================================================
    # 5. FORMATAÇÃO E MAPEAMENTO
    # ==========================================================
    try:
        # Aqui convertemos o JSON "Plano" da nova API para o objeto hierárquico
        # que o seu Front-end (buscarplaca.html) espera receber.
        
        resposta_formatada = {
            "dados_principais": {
                "placa": dados_api.get('placa'),
                "chassi": dados_api.get('chassi'),
                "renavam": dados_api.get('codigoRenavam'), # Nome novo
                "municipio": dados_api.get('descricaoMunicipioEmplacamento'),
                "uf": dados_api.get('ufJurisdicao'),
                "situacao": dados_api.get('situacao', '---').replace('_', ' ')
            },
            "caracteristicas": {
                "marca_modelo": dados_api.get('descricaoMarcaModelo'),
                "ano_fab": dados_api.get('anoFabricacao'),
                "ano_mod": dados_api.get('anoModelo'),
                "cor": dados_api.get('descricaoCor'),
                "combustivel": dados_api.get('descricaoCombustivel'),
                "motor": dados_api.get('numeroMotor'),
                "potencia": dados_api.get('potencia'),
                "cilindradas": dados_api.get('cilindradas')
            },
            "proprietario": {
                "nome": dados_api.get('nomeProprietario'),
                "cpf_cnpj": dados_api.get('numeroIdentificacaoProprietario')
            },
            "restricoes": {
                "restricao_1": dados_api.get('descricaoRestricao1'),
                "roubo_furto": bool_to_text(dados_api.get('indicadorRouboFurto')),
                "restricao_renajud": bool_to_text(dados_api.get('indicadorRestricaoRenajud')),
                "multa_renainf": bool_to_text(dados_api.get('indicadorMultaRenainf'))
            },
            "datas": {
                # Usa o helper limpar_data para remover o horário T...
                "dt_crv": formatar_data(limpar_data(dados_api.get('dataEmissaoCrv'))),
                "dt_crlv": formatar_data(limpar_data(dados_api.get('dataEmissaoCRLV'))),
                "licenciamento": dados_api.get('anoExercicioLicenciamentoPago')
            }
        }
    except Exception as e:
        current_app.logger.error(f"❌ Erro ao formatar dados da API: {e}")
        return jsonify({'error': 'Erro ao processar dados do veículo.'}), 500

    # ==========================================================
    # 6. SALVAMENTO NO CACHE
    # ==========================================================
    # Só salva se NÃO for Mock (para não sujar o banco com dados falsos)
    if not usar_mock:
        try:
            agora = datetime.now(timezone.utc)
            # Verifica existência novamente (Race condition check)
            existe = g.db.query(CachePlaca).filter_by(placa=placa).first()
            
            if not existe:
                novo_cache = CachePlaca(placa=placa, dados_json=resposta_formatada, data_consulta=agora)
                g.db.add(novo_cache)
                g.db.commit()
                current_app.logger.info(f"💾 [CACHE SAVE] Placa {placa} salva.")
                
        except Exception as e:
            g.db.rollback()
            current_app.logger.error(f"❌ Falha ao salvar cache: {e}")

    # Registra log final
    registrar_log(current_user.id, 'CONSULTA PLACA (API)', f'Placa: {placa}')
    
    return jsonify({
        'status': 'sucesso', 
        'origem': 'api_mock' if usar_mock else 'api',
        'data': resposta_formatada
    })
    

# ==========================================
# ROTA DE CONSULTA CPF (MANTIDA)
# ==========================================

# 1. Rota para exibir a página HTML
@consultas_bp.route('/consultar-cpf')
@login_required
@requer_modulo_ativo('consultas.view_consultar_cpf')
def view_consultar_cpf():
    return render_template('consultarcpf.html')

# 2. Rota da API (Backend que busca os dados)
@consultas_bp.route('/api/consultar-cpf', methods=['POST'])
@login_required
def api_consultar_cpf():
    # 1. Identificação do IP
    if request.headers.getlist("X-Forwarded-For"):
        user_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        user_ip = request.remote_addr
      
    # 2. Processamento
    data = request.get_json()
    cpf = data.get('cpf')
    
    if not cpf: 
        return jsonify({'error': 'CPF obrigatório'}), 400

    cpf_limpo = re.sub(r'[^0-9]', '', cpf)

    # 3. Chamada API Externa
    API_KEY = os.getenv('GONZALES_API_KEY')
    
    if not API_KEY:
        current_app.logger.error("Chave GONZALES_API_KEY não encontrada")
        return jsonify({'error': 'Erro interno: Chave de API não configurada'}), 500

    # CORREÇÃO 1: O parâmetro correto segundo seu link é cpf_credilink
    url = f"https://consultasgonzales.com/apis/?apikey={API_KEY}&cpf_credilink={cpf_limpo}"

    try:
        response = requests.get(url, timeout=20)
        
        if response.status_code != 200:
            return jsonify({'error': 'Erro na comunicação com a API externa.'}), 502
            
        dados_api = response.json()
        
        # CORREÇÃO 2: A validação baseada no JSON que você enviou
        # O JSON retorna "ok": true e "encontrado": true
        if not dados_api.get('ok') or not dados_api.get('encontrado'):
            return jsonify({'error': 'CPF não encontrado ou inválido.'}), 404
            
        registrar_log(
            usuario_id=current_user.id,
            acao='CONSULTA CPF',
            detalhes=f'CPF Consultado: {cpf_limpo}'
        )

        # CORREÇÃO 3: Mapear os dados corretamente
        # O JSON separa "dados_cadastrais" e "telefones"
        resposta_final = dados_api.get('dados_cadastrais', {})
        
        # Injetamos os telefones dentro do objeto de resposta para o frontend usar
        if 'telefones' in dados_api:
            resposta_final['telefones'] = dados_api.get('telefones')

        return jsonify({
            'status': 'success',
            'data': resposta_final
        })

    except Exception as e:
        current_app.logger.error(f"Erro na consulta de CPF ({cpf_limpo}): {e}")
        return jsonify({'error': 'Erro interno ao processar consulta.'}), 500