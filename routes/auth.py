import os
import requests
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, g, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import uuid

# Imports Locais
from models import Usuario
from forms import LoginForm
from utils import registrar_log

auth_bp = Blueprint('auth', __name__)

# =================================================================
# FUNÇÃO AUXILIAR DO CLOUDFLARE TURNSTILE
# =================================================================
def verificar_turnstile(token):
    """Valida o token do Turnstile com a API da Cloudflare."""
    SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY')
    
    if not token:
        return False
        
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                'secret': SECRET_KEY,
                'response': token,
                'remoteip': request.remote_addr
            },
            timeout=5 # Timeout por segurança
        )
        resultado = response.json()
        return resultado.get('success', False)
    except Exception as e:
        print(f"Erro ao validar Turnstile: {e}")
        return False


# -----------------------------------------------------------------
# ROTA DE LOGIN (COM CAPTCHA CLOUDFLARE)
# -----------------------------------------------------------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    
    # --- GET: Renderiza página e verifica Sessão Zumbi ---
    if request.method == 'GET':
        
        # 1. VACINA ANTI-LOOP (SÓ NO GET)
        if current_user.is_authenticated:
            token_navegador = session.get('user_token')
            sessao_valida = False

            if hasattr(g, 'db') and token_navegador:
                try:
                    user_db = g.db.get(Usuario, int(current_user.id))
                    if user_db and user_db.session_token == token_navegador:
                        sessao_valida = True
                except:
                    pass 

            if sessao_valida:
                return redirect(url_for('main.home'))
            else:
                # Limpa a sessão zumbi
                logout_user()
                session.clear()
        
        # 2. CRIA O FORMULÁRIO AGORA (DEPOIS DO SESSION.CLEAR)
        form = LoginForm()

        # 3. PUXA A CHAVE PÚBLICA PARA O HTML
        site_key = os.getenv('TURNSTILE_SITE_KEY')

        # Renderiza a página enviando a chave do Captcha
        return render_template(
            'login.html',
            form=form,
            mensagem_erro=None,
            site_key=site_key
        )

    # --- POST: Processa Login ---
    if request.method == 'POST':
        form = LoginForm(request.form)
        
        if form.validate():
            
            # ==========================================================
            # 🛡️ BARREIRA CLOUDFLARE TURNSTILE ANTES DO BANCO DE DADOS
            # ==========================================================
            turnstile_token = request.form.get('cf-turnstile-response')
            
            if not verificar_turnstile(turnstile_token):
                return jsonify({
                    'success': False, 
                    'error': '🤖 Falha na verificação de segurança. Prove que é humano e tente novamente.'
                }), 400
            
            # ==========================================================
            # Autenticação
            # ==========================================================
            email = form.email.data
            senha = form.senha.data
            
            # Busca no banco
            usuario = g.db.query(Usuario).filter_by(email=email).first()

            # Verificação de senha
            if usuario and check_password_hash(usuario.senha_hash, senha):
                
                # --- Verificações de Status/Validade ---
                if usuario.status == 'pendente':
                    return jsonify({'success': False, 'error': '⏳ Sua conta está aguardando aprovação.'}), 401
                if usuario.status == 'rejeitado':
                    return jsonify({'success': False, 'error': '🚫 Sua solicitação de acesso foi rejeitada.'}), 401
                
                is_expired = False
                if usuario.validade:
                    validade_aware = usuario.validade
                    if validade_aware.tzinfo is None:
                        validade_aware = validade_aware.replace(tzinfo=timezone.utc)
                    if validade_aware < datetime.now(timezone.utc):
                        is_expired = True
                
                if is_expired:
                    return jsonify({'success': False, 'error': '⏰ Seu tempo de acesso ao painel expirou.'}), 401

                # ==========================================================
                # SESSÃO ÚNICA (SINGLE SESSION)
                # ==========================================================
                try:
                    # Gera novo token
                    novo_token = str(uuid.uuid4())
                    usuario.session_token = novo_token
                    g.db.commit()
                    
                    # Limpa sessão anterior e define a nova
                    session.clear() 
                    session['user_token'] = novo_token
                except Exception as e:
                    g.db.rollback()
                    return jsonify({'success': False, 'error': 'Erro ao gerar sessão segura.'}), 500

                # --- SUCESSO: INICIA SESSÃO FLASK ---
                remember_me = True if usuario.admin else False
                session.permanent = remember_me
                
                login_user(usuario, remember=remember_me)
                
                session['usuario_id'] = usuario.id
                session['usuario_nome'] = usuario.nome
                session['admin'] = usuario.admin
                session['pode_cadastrar'] = usuario.pode_cadastrar
                session['pode_editar'] = usuario.pode_editar
                session['pode_excluir'] = usuario.pode_excluir
                session['mostrar_boas_vindas'] = True

                return jsonify({'success': True, 'redirect_url': url_for('main.home')})
            else:
                return jsonify({'success': False, 'error': 'Email ou senha incorretos!'}), 401
        
        else:
            primeiro_erro = next(iter(form.errors.values()))[0]
            return jsonify({'success': False, 'error': f"⚠️ {primeiro_erro}"}), 400

    return jsonify({'success': False, 'error': 'Método não permitido.'}), 405

# -----------------------------------------------------------------
# ROTA LOGOUT
# -----------------------------------------------------------------
@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    
    response = redirect(url_for('auth.login'))
    response.delete_cookie('session')
    response.delete_cookie('remember_token')
    
    return response