# 🔍 Buscar Veículos

Sistema web completo para **cadastro, busca e gerenciamento de veículos**, com controle de acesso por usuário e registro de ações. Ideal para empresas que precisam consultar RENAVAM e CPF de veículos por modelo — como no cadastro de motoristas em apps como a 99.

---

##  Funcionalidades

- 🔐 Login com verificação por senha e CAPTCHA (Turnstile)
- 👥 Gestão de usuários com permissões:
  - Administrador
  - Cadastro, edição e exclusão de veículos
- 🚗 Cadastro de veículos com:
  - Modelo, RENAVAM, CPF/CNPJ, ano, cor
  - Upload de CRLV (PDF/TXT) para o Cloudinary
- 🔎 Busca de veículos por **modelo**
- ✏️ Edição e exclusão de registros
- 📝 Logs de auditoria completos (consultas, cadastros, alterações)
- 🌐 Painel intuitivo com módulos de busca
- ⚠️ Proteções de segurança: headers HTTP, rate limit, sessões seguras

---

## 🧪 Tecnologias utilizadas

- [Python 3](https://www.python.org/)
- [Flask](https://flask.palletsprojects.com/)
- [PostgreSQL](https://www.postgresql.org/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Flask-Session](https://flask-session.readthedocs.io/)
- [Flask-Limiter](https://flask-limiter.readthedocs.io/)
- [Cloudinary](https://cloudinary.com/)
- [dotenv](https://pypi.org/project/python-dotenv/)
- Turnstile (Cloudflare) – para CAPTCHA

---

## 🚀 Deploy

Este projeto está disponível em produção via Render:

👉 **[buscar-veiculos.onrender.com](https://buscar-veiculos.onrender.com)**

> ⚠️ Login necessário. Acesso mediante permissão do autor.

---

## 🧰 Como rodar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/ThadeuAngelo/buscar-veiculos.git
cd buscar-veiculos

# 2. Crie e ative um ambiente virtual
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure suas variáveis de ambiente no arquivo .env
# Veja .env.example (caso exista)

# 5. Execute a aplicação
python app.py


## 🗃️ Estrutura de pastas (resumida)
buscar-veiculos/
├── app.py                # Código principal Flask
├── models.py             # Modelos SQLAlchemy (Veiculo, Usuario, LogAuditoria)
├── templates/            # Arquivos HTML (Jinja2)
├── static/               # CSS, JS, imagens
├── requirements.txt      # Dependências do projeto
├── .env                  # Variáveis de ambiente


📌 Observações
As rotas de consulta por placa e CPF estão em desenvolvimento.

A aplicação possui logs de auditoria para rastrear todas as ações dos usuários.

O acesso ao painel é restrito e pode ser limitado por tempo.


👤 Autor
Desenvolvido por João Thadeu Angelo
📫 github.com/joaothadeuangelo
📧 joaothadeuangelo@gmail.com


📄 Licença MIT - Este é um projeto de portfólio para fins de estudo e demonstração técnica. Sinta-se à vontade para explorar o código ou fazer um fork.



