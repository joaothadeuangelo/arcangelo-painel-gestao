from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

# -------------------------------------------------------------------
# DECORATOR: Exige ser ADMIN
# -------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.admin:
            flash('Acesso não autorizado. Área restrita a administradores.', 'error')
            return redirect(url_for('main.home')) 
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# DECORATOR: Exige permissão de CADASTRO
# -------------------------------------------------------------------
def cadastro_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.pode_cadastrar:
            flash('Você não tem permissão para cadastrar veículos.', 'error')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# DECORATOR: Exige permissão de EDIÇÃO
# -------------------------------------------------------------------
def edicao_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.pode_editar:
            flash('Acesso negado: você não tem permissão para editar.', 'error')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# DECORATOR: Exige permissão de EXCLUSÃO
# -------------------------------------------------------------------
def exclusao_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.pode_excluir:
            flash('Acesso negado: você não tem permissão para excluir.', 'error')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# DECORATOR: Exige estar DESLOGADO (Logout Required)
# -------------------------------------------------------------------
def logout_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            # Se já está logado, manda pro painel
            return redirect(url_for('main.home')) 
        return f(*args, **kwargs)
    return decorated_function