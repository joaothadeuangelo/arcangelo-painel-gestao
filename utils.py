import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash
from flask import current_app
from models import Modulo
from functools import wraps
from flask import g, flash, redirect, url_for, request, jsonify
from flask_login import current_user
from models import Modulo

# Imports do projeto
from database import SessionLocal
from models import LogAuditoria, Usuario

# -----------------------------------------------------
# 1. FUNÇÃO DE LOG DE AUDITORIA
# -----------------------------------------------------
def registrar_log(usuario_id, acao, detalhes=None):
    """
    Registra uma ação no banco de dados de forma independente.
    IGNORA se o usuário for 'admin@admin'.
    """
    session = SessionLocal()
    
    try:
        # 1. Busca o usuário
        usuario = session.query(Usuario).filter_by(id=usuario_id).first()

        # 2. Ignora Admin Supremo
        if usuario and usuario.email == "admin@admin":
            return 

        # 3. Cria Log
        novo_log = LogAuditoria(
            usuario_id=usuario_id,
            acao=acao,
            detalhes=detalhes,
            timestamp=datetime.now(timezone.utc)
        )
        
        session.add(novo_log)
        session.commit()

    except Exception as e:
        session.rollback()
        print(f"❌ Erro silencioso ao registrar log: {e}")

    finally:
        session.close()

# -----------------------------------------------------
# 2. FILTRO DE DATA (BR TIME)
# -----------------------------------------------------
# Nota: Removemos o @app.template_filter. O registro é feito no app.py
def formatar_horario_br(valor_data):
    if not valor_data:
        return ''

    try:
        if isinstance(valor_data, str):
            try:
                dt_obj = datetime.fromisoformat(valor_data)
            except ValueError:
                dt_obj = datetime.strptime(valor_data, "%Y-%m-%d %H:%M:%S")
        else:
            dt_obj = valor_data

        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)

        sp_tz = ZoneInfo("America/Sao_Paulo")
        dt_brasil = dt_obj.astimezone(sp_tz)

        return dt_brasil.strftime('%d/%m/%Y %H:%M:%S')

    except Exception as e:
        print(f"Erro no filtro 'brtime': {e} | Valor: {valor_data}")
        return "Erro data"

# -----------------------------------------------------
# 3. INJETOR DE DATA ATUAL
# -----------------------------------------------------
# Nota: Removemos o @app.context_processor. O registro é feito no app.py
def inject_now():
    return {'now': datetime.now(timezone.utc)}

# -----------------------------------------------------
# 4. VERIFICAR/CRIAR ADMIN
# -----------------------------------------------------
def verificar_criar_admin():
    """Verifica se existe admin, se não, cria o padrão."""
    db = SessionLocal()
    try:
        admin_existente = db.query(Usuario).filter_by(admin=True).first()

        if not admin_existente:
            admin_password = os.getenv("ADMIN_DEFAULT_PASSWORD")
            if not admin_password:
                print("⚠️ ADMIN_DEFAULT_PASSWORD não definida. Admin automático não será criado.")
                return

            print("👤 Usuário admin não encontrado. Criando um novo...")
            admin_user = Usuario(
                nome='Admin Principal',
                email='admin@admin',
                senha=generate_password_hash(admin_password, method='pbkdf2:sha256'),
                admin=True,
                pode_cadastrar=True,
                pode_editar=True,
                pode_excluir=True,
                status='aprovado',
                validade=None
            )
            db.add(admin_user)
            db.commit()
            print("✅ Usuário admin padrão criado! (admin@admin / senha via ADMIN_DEFAULT_PASSWORD)")
        else:
            print("👤 Usuário admin já existe.")
    except Exception as e:
        print(f"❌ Erro ao verificar admin: {e}")
    finally:
        db.close()


# -----------------------------------------------------
# 5. FORMATADOR DE DATA API (DD/MM/YYYY)
# -----------------------------------------------------
def formatar_data(data_str):
    """
    Tenta formatar datas que vêm de APIs (YYYY-MM-DD ou ISO) para DD/MM/YYYY
    """
    if not data_str: return "---"
    try:
        # Tenta pegar apenas a data se vier com hora (2025-03-12T12:53:28)
        data_limpa = str(data_str).split('T')[0] 
        dt = datetime.strptime(data_limpa, '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    except:
        return str(data_str)
    

def requer_modulo_ativo(nome_rota_db):
    """
    Bloqueia o acesso à rota se o módulo estiver em manutenção no banco.
    Admins têm acesso VIP (ignoram o bloqueio).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Se for Admin, PASS LIVRE (pode entrar mesmo em manutenção)
            if current_user.is_authenticated and current_user.admin:
                return f(*args, **kwargs)

            # 2. Busca o módulo no banco pelo nome da rota (ex: 'consultas.buscar')
            try:
                modulo = g.db.query(Modulo).filter_by(rota=nome_rota_db).first()
            except:
                modulo = None

            # 3. Se o módulo existe e está em 'manutencao', BARRA A ENTRADA
            if modulo and modulo.status == 'manutencao':
                
                # Se a requisição for API/AJAX (Retorna JSON)
                if request.is_json or '/api/' in request.path:
                    return jsonify({'error': '⚠️ Módulo em manutenção técnica. Tente mais tarde.'}), 503
                
                # Se a requisição for Navegador (Retorna para a Home com aviso)
                flash('⚠️ Este módulo está em manutenção momentânea.', 'warning')
                return redirect(url_for('main.home'))

            # Se estiver Online (ou não cadastrado nos módulos), deixa passar
            return f(*args, **kwargs)
        return decorated_function
    return decorator