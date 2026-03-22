from flask_wtf import FlaskForm
# ADICIONEI 'SubmitField' NA LISTA ABAIXO:
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length

# 10. CLASSE DE FORMULÁRIO DE LOGIN
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    senha = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')