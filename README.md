# OliverFlow — Pet Shop Oliver's

Sistema web interno (*backoffice*) para gestão de agendamentos, fila diária de atendimento (banho, tosa, terapias e creche), cadastro de tutores/pets e baixa presencial de pagamentos.

## Stack Tecnológica
- **Backend:** Python 3.11+ · Flask · Jinja2
- **Banco de Dados:** MySQL (`oliverflow_db` na porta `3306`) · Flask-SQLAlchemy · PyMySQL
- **Segurança:** Werkzeug (`generate_password_hash` / `check_password_hash`), proteção CSRF, bloqueio temporário por tentativas de login (ISO/IEC 27002) e exclusão/anonimização compatível com a LGPD
- **Frontend & Acessibilidade:** HTML5 Semântico · CSS3 · Bootstrap 5 · JavaScript (ES6+) em conformidade com a **ABNT NBR 17225:2025 / WCAG 2.2**

## Como executar localmente

1. Inicie o serviço **MySQL** no XAMPP Control Panel (porta `3306`).
2. Ative o ambiente virtual e instale as dependências:
   ```powershell
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Crie o banco `oliverflow_db`, as 6 tabelas e os dados iniciais de teste:
   ```powershell
   python seed.py --reset
   ```
4. Inicie o servidor Flask:
   ```powershell
   python app.py
   ```
5. Acesse `http://127.0.0.1:5000` no navegador.

## Credenciais iniciais (seed)
| Perfil | Login | Senha | Permissões |
|---|---|---|---|
| **Admin** (Proprietário) | `jefferson` | `Oliver@2026` | Acesso total (Início/Fila, Agenda Semanal, Tutores/Pets, Faturamento/Histórico, Catálogo de Serviços e Equipe) |
| **Atendente** (Operacional) | `atendente` | `Atende@2026` | Acesso operacional (Início/Fila, Agenda Semanal, Tutores/Pets e Baixa de Pagamento) |
