import re
import random
import string
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, current_app
from werkzeug.security import generate_password_hash
from flask_login import current_user

# Imports do Projeto
from models import Usuario, LogAuditoria, BuscaSemResultado
from decorators import admin_required
from utils import registrar_log
from flask import jsonify
from sqlalchemy.orm import joinedload
from sqlalchemy import func

# Define o Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# --------------------------------------------------------------------
# 1. LISTAR USUÁRIOS (LÓGICA SEU CÓDIGO: FILTRO + ORDEM ALFABÉTICA)
# --------------------------------------------------------------------
@admin_bp.route('/usuarios')
@admin_required
def listar_usuarios():
    # 1. Filtra != 'inativo' e Ordena por Nome
    usuarios = g.db.query(Usuario).filter(Usuario.status != 'inativo').order_by(Usuario.nome).all()

    # Ajuste de timezone para exibição
    for usuario in usuarios:
        if usuario.validade and usuario.validade.tzinfo is None:
            usuario.validade = usuario.validade.replace(tzinfo=timezone.utc)

    return render_template('usuarios.html', usuarios=usuarios, now=datetime.now(timezone.utc))

# --------------------------------------------------------------------
# 2. CRIAR NOVO USUÁRIO
# --------------------------------------------------------------------
@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@admin_required
def criar_usuario():
    if request.method == 'POST':
        try:
            nome = request.form['nome'].strip()
            prefixo = request.form.get('email_prefixo', '').strip()
            
            # Gera senha aleatória: Arc# + 8 números
            senha_plana = 'Arc#' + ''.join(random.choices(string.digits, k=8))

            if not nome or not prefixo:
                flash('Todos os campos obrigatórios devem ser preenchidos!', 'error')
                return redirect(url_for('admin.criar_usuario'))

            # --- Permissões ---
            eh_admin = 'admin' in request.form
            if eh_admin:
                email = f"{prefixo}@admin"
                pode_cadastrar = True
                pode_editar = True
                pode_excluir = True
            else:
                email = f"{prefixo}@painel"
                pode_cadastrar = 'pode_cadastrar' in request.form
                pode_editar = 'pode_editar' in request.form
                pode_excluir = 'pode_excluir' in request.form

            # --- Validade ---
            acesso_ilimitado = 'acesso_ilimitado' in request.form
            validade = None

            if not acesso_ilimitado:
                valor = request.form.get('tempo_val')
                tipo = request.form.get('tempo_tipo')
                if valor and tipo:
                    try:
                        valor = int(valor)
                        agora = datetime.now(timezone.utc)
                        if tipo == 'horas': validade = agora + timedelta(hours=valor)
                        elif tipo == 'dias': validade = agora + timedelta(days=valor)
                        elif tipo == 'meses': validade = agora + timedelta(days=30*valor)
                    except ValueError:
                        flash('Tempo de acesso inválido.', 'error')
                        return redirect(url_for('admin.criar_usuario'))

            # --- Duplicidade ---
            if g.db.query(Usuario).filter_by(email=email).first():
                flash(f'Já existe um usuário com o e-mail {email}.', 'error')
                return redirect(url_for('admin.criar_usuario'))

            # --- Inserção ---
            novo_usuario = Usuario(
                nome=nome,
                email=email,
                senha_hash=generate_password_hash(senha_plana),
                admin=eh_admin,
                pode_cadastrar=pode_cadastrar,
                pode_editar=pode_editar,
                pode_excluir=pode_excluir,
                validade=validade,
                status='aprovado'
            )
            g.db.add(novo_usuario)
            g.db.commit()

            # Sessão para Modal
            session['dados_novo_usuario'] = {
                "email": email,
                "senha": senha_plana,
                "validade": validade.strftime('%d/%m/%Y %H:%M') if validade else "Ilimitado",
                "link": url_for('auth.login', _external=True) 
            }
            
            registrar_log(current_user.id, "Criação de usuário", f"Criado: {email}")
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('admin.listar_usuarios'))

        except Exception as e:
            g.db.rollback()
            flash(f'Erro ao criar usuário: {e}', 'error')

    return render_template('criar_usuario.html')

# --------------------------------------------------------------------
# 3. EDITAR USUÁRIO
# --------------------------------------------------------------------
@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(id):
    usuario = g.db.query(Usuario).filter_by(id=id).first()
    if not usuario:
        flash('Usuário não encontrado!', 'error')
        return redirect(url_for('admin.listar_usuarios'))

    if request.method == 'POST':
        try:
            nome = request.form['nome'].strip()
            prefixo = request.form.get('email_prefixo', '').strip()
            telefone_bruto = request.form.get('telefone', '').strip()
            telefone_limpo = re.sub(r'\D', '', telefone_bruto)

            if not nome or not prefixo:
                flash('Nome e prefixo são obrigatórios!', 'error')
                return redirect(url_for('admin.editar_usuario', id=id))

            usuario.nome = nome
            usuario.telefone = telefone_limpo

            # --- Permissões ---
            eh_admin = 'admin' in request.form
            
            if eh_admin:
                if '@' in prefixo:
                    email = prefixo
                    if not (email.endswith('@admin') or email.endswith('@staff')):
                        flash('Admins devem usar @admin ou @staff', 'error')
                        return redirect(url_for('admin.editar_usuario', id=id))
                else:
                    email = f"{prefixo}@admin"
                
                usuario.pode_cadastrar = True
                usuario.pode_editar = True
                usuario.pode_excluir = True
            else:
                email = f"{prefixo}@painel"
                usuario.pode_cadastrar = 'pode_cadastrar' in request.form
                usuario.pode_editar = 'pode_editar' in request.form
                usuario.pode_excluir = 'pode_excluir' in request.form

            # Verifica duplicidade
            outro = g.db.query(Usuario).filter(Usuario.email == email, Usuario.id != id).first()
            if outro:
                flash(f'O e-mail {email} já está em uso.', 'error')
                return redirect(url_for('admin.editar_usuario', id=id))

            usuario.email = email
            usuario.admin = eh_admin

            # Senha
            senha = request.form['senha'].strip()
            if senha:
                usuario.senha_hash = generate_password_hash(senha)

            # --- Validade ---
            if 'acesso_ilimitado' in request.form:
                usuario.validade = None
                if usuario.status == 'banido': usuario.status = 'aprovado'
            else:
                valor = request.form.get('tempo_val')
                tipo = request.form.get('tempo_tipo')
                if valor and tipo:
                    try:
                        valor = int(valor)
                        base_time = usuario.validade or datetime.now(timezone.utc)
                        if usuario.status == 'banido': base_time = datetime.now(timezone.utc)
                        
                        if base_time.tzinfo is None: base_time = base_time.replace(tzinfo=timezone.utc)

                        if tipo == 'horas': usuario.validade = base_time + timedelta(hours=valor)
                        elif tipo == 'dias': usuario.validade = base_time + timedelta(days=valor)
                        elif tipo == 'meses': usuario.validade = base_time + timedelta(days=30*valor)
                    except ValueError:
                         pass

            # Reativa se ganhou tempo
            if usuario.status == 'banido' and usuario.validade and usuario.validade > datetime.now(timezone.utc):
                usuario.status = 'aprovado'

            g.db.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            registrar_log(current_user.id, "Edição de usuário", f"Editado: {email}")

        except Exception as e:
            g.db.rollback()
            flash(f'Erro ao atualizar: {e}', 'error')
            return redirect(url_for('admin.editar_usuario', id=id))

        return redirect(url_for('admin.listar_usuarios'))

    if usuario.validade and usuario.validade.tzinfo is None:
        usuario.validade = usuario.validade.replace(tzinfo=timezone.utc)
        
    return render_template('editar_usuario.html', usuario=usuario, now=datetime.now(timezone.utc))

# --------------------------------------------------------------------
# 4. EXCLUIR (DESATIVAR) USUÁRIO - (LÓGICA SEU CÓDIGO)
# --------------------------------------------------------------------
@admin_bp.route('/usuarios/excluir/<int:id>', methods=['POST'])
@admin_required
def excluir_usuario(id):
    # Proteção auto-exclusão
    if id == session.get('usuario_id'):
        flash('Você não pode desativar a si mesmo.', 'error')
        return redirect(url_for('admin.listar_usuarios'))

    try:
        usuario = g.db.query(Usuario).filter_by(id=id).first()

        if usuario:
            nome_usuario_excluido = usuario.nome

            # SOFT DELETE: Muda status para inativo
            usuario.status = 'inativo' 
            g.db.commit()

            # Log
            registrar_log(
                usuario_id=session['usuario_id'],
                acao="Desativação de usuário",
                detalhes=f"Usuário desativado: {nome_usuario_excluido} (ID: {id})"
            )

            flash('Usuário desativado com sucesso!', 'success')
        else:
            flash('Usuário não encontrado.', 'error')

    except Exception as e:
        g.db.rollback()
        # app.logger não está disponível direto aqui, usamos print ou current_app
        print(f"❌ Erro ao desativar usuário ID {id}: {e}")
        flash('Ocorreu um erro ao tentar desativar o usuário.', 'error')

    return redirect(url_for('admin.listar_usuarios'))

# -------------------------------------------------------
# ROTA PARA CARREGAR A PÁGINA DE AUDITORIA (A "CASCA")
# -------------------------------------------------------
@admin_bp.route('/auditoria')
@admin_required
def auditoria():
    """Renderiza a página principal de auditoria, que será preenchida via AJAX."""
    
    # Busca as ações disponíveis para preencher o filtro
    acoes_disponiveis = [acao[0] for acao in g.db.query(LogAuditoria.acao).distinct().order_by(LogAuditoria.acao).all()]
    
    # Atualiza a hora da última visualização dos logs (Lógica mantida)
    usuario_admin = g.db.query(Usuario).filter_by(id=session['usuario_id']).first()
    if usuario_admin:
        usuario_admin.ultimo_log_visto = datetime.now(timezone.utc)
        g.db.commit()
        
    return render_template('auditoria.html', acoes_disponiveis=acoes_disponiveis)

# -------------------------------------------------------
# NOVA ROTA DE API PARA BUSCAR OS LOGS E ENVIAR COMO JSON
# -------------------------------------------------------
@admin_bp.route('/api/auditoria')
@admin_required
def api_auditoria():
    """Busca, filtra e pagina os logs, retornando os dados em JSON."""
    
    # Captura parâmetros da URL (GET)
    page = request.args.get('page', 1, type=int)
    filtro_usuario = request.args.get('filtro_usuario', '', type=str).strip()
    filtro_acao = request.args.get('filtro_acao', '', type=str).strip()
    per_page = 15

    # Monta a query inicial
    # options(joinedload...) otimiza para trazer o Usuario junto numa tacada só
    query = g.db.query(LogAuditoria).options(joinedload(LogAuditoria.usuario))

    # Aplica filtros se existirem
    if filtro_usuario:
        query = query.join(Usuario).filter(Usuario.nome.ilike(f"%{filtro_usuario}%"))
    if filtro_acao:
        query = query.filter(LogAuditoria.acao == filtro_acao)

    # Lógica de Contagem Otimizada
    try:
        # Tenta contar rápido via SQL puro
        count_q = query.statement.with_only_columns(func.count()).order_by(None)
        total_logs = g.db.execute(count_q).scalar()
    except Exception:
        total_logs = query.count() # Fallback se der erro

    total_pages = (total_logs + per_page - 1) // per_page
    
    # Busca os resultados paginados
    logs_paginados = query.order_by(LogAuditoria.timestamp.desc()).limit(per_page).offset((page - 1) * per_page).all()
    
    # Converte para dicionário (JSON) usando o método do seu Model
    logs_dict = [log.to_dict() for log in logs_paginados]

    return jsonify({
        'logs': logs_dict,
        'page': page,
        'total_pages': total_pages,
        'total_logs': total_logs
    })


# -----------------------------------------------------
# ROTA PARA BANIR um usuário (ATUALIZADA)
# -----------------------------------------------------
@admin_bp.route('/usuarios/banir/<int:id>', methods=['POST'])
@admin_required
def banir_usuario(id):
    # Impede que o admin bana a si mesmo
    if id == session.get('usuario_id'):
        flash('❌ Você não pode banir a si mesmo.', 'error')
        return redirect(url_for('admin.listar_usuarios'))

    try:
        usuario = g.db.query(Usuario).filter_by(id=id).first()

        if not usuario:
            flash('❌ Usuário não encontrado.', 'error')
            return redirect(url_for('admin.listar_usuarios'))

        # Lógica de Banimento
        # Define a validade no passado para invalidar a sessão
        usuario.validade = datetime.now(timezone.utc) - timedelta(days=1)
        usuario.status = 'banido'

        g.db.commit()

        flash(f"✅ Usuário {usuario.nome} foi banido com sucesso.", 'success')

        registrar_log(
            usuario_id=session['usuario_id'],
            acao="Banimento de usuário",
            detalhes=f"Usuário banido: {usuario.nome} (ID: {usuario.id})"
        )

    except Exception as e:
        g.db.rollback()
        # app.logger não está disponível aqui, usamos print
        print(f"❌ Erro ao banir usuário ID {id}: {e}")
        flash(f'❌ Erro ao banir usuário: {e}', 'error')

    return redirect(url_for('admin.listar_usuarios'))


# --------------------------------------------------------
# ROTA API DEMANDAS
# --------------------------------------------------------
@admin_bp.route('/api/demandas', methods=['GET'])
@admin_required
def api_demandas():
    """
    Endpoint da API que retorna uma lista detalhada das buscas sem resultado.
    """
    try:
        # Busca demandas pendentes com o nome do usuário
        demandas = g.db.query(
            BuscaSemResultado,
            Usuario.nome.label('nome_usuario')
        ).join(
            Usuario, BuscaSemResultado.usuario_id == Usuario.id
        ).filter(
            BuscaSemResultado.status == 'pendente'
        ).order_by(
            BuscaSemResultado.data_hora.desc()
        ).all()

        # Formata para JSON
        resultados_json = [
            {
                'id': demanda.id,
                'termo': demanda.termo_pesquisado,
                'usuario': nome_usuario,
                'data_hora': demanda.data_hora.strftime('%d/%m/%Y %H:%M:%S')
            }
            for demanda, nome_usuario in demandas
        ]

        return jsonify(resultados_json)

    except Exception as e:
        # current_app substitui app.logger aqui
        current_app.logger.error(f"Erro ao buscar demandas da API: {e}")
        return jsonify({"erro": "Ocorreu um erro interno."}), 500

# ---------------------------------------------------------------------------------------
# EXIBE PÁGINA DE DEMANDAS
# ---------------------------------------------------------------------------------------
@admin_bp.route('/demandas')
@admin_required
def demandas_page():
    return render_template('demandas.html')

# ----------------------------------------------------------
# ROTA QUE MARCA COMO CONCLUÍDO
# ----------------------------------------------------------
@admin_bp.route('/demandas/marcar-concluido', methods=['POST'])
@admin_required
def marcar_demanda_concluida():
    data = request.get_json()
    termo_pesquisado = data.get('termo')

    if not termo_pesquisado:
        return jsonify({"sucesso": False, "erro": "Termo não fornecido."}), 400

    try:
        # Atualiza status no banco
        g.db.query(BuscaSemResultado).filter(
            BuscaSemResultado.termo_pesquisado == termo_pesquisado
        ).update({"status": "concluido"})

        g.db.commit()

        # Log de sucesso
        current_app.logger.info(f"Demandas para '{termo_pesquisado}' concluídas.")
        return jsonify({"sucesso": True, "mensagem": "Demanda marcada como concluída."})

    except Exception as e:
        g.db.rollback()
        current_app.logger.error(f"Erro ao concluir demanda: {e}")
        return jsonify({"sucesso": False, "erro": "Erro interno no servidor."}), 500