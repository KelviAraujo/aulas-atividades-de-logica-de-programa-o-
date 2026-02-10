# Sistema de Cadastro de Clientes (controle_system)

Rápido sistema de cadastro de clientes (backend em Flask + SQLite) com validação.

Como rodar (Windows):

1. Criar e ativar um ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r controle_system/requirements.txt
```

2. Rodar a aplicação

```powershell
python controle_system/app.py
```

3. Abrir http://127.0.0.1:5000/

Testes:

```powershell
pip install -r controle_system/requirements.txt
pytest -q

Autenticação API key
- Configure a variável de ambiente `APP_API_KEY` para ativar proteção das rotas de criação/atualização/exclusão e import/export.

Exemplo (PowerShell):

```powershell
$env:APP_API_KEY = 'minha-chave-secreta'
python d:/PROGRAMAÇÃO-AULA/controle_system/app.py
```

Export CSV (curl):

```powershell
curl -H "X-API-KEY: minha-chave-secreta" http://127.0.0.1:5000/api/customers/export -o clientes.csv
```

Import CSV (curl):

```powershell
curl -H "X-API-KEY: minha-chave-secreta" -F file=@clientes.csv http://127.0.0.1:5000/api/customers/import
```

Autenticação de usuários (sessão + token)
- Registre via `/auth/register` com JSON `{ "username":"u", "email":"e","password":"p" }`.
- Faça login via `/auth/login` com JSON `{ "username":"u","password":"p" }`. Retorna `token` (Bearer) e cria sessão.
- Rotas protegidas aceitam: sessão autenticada, header `X-API-KEY` ou `Authorization: Bearer <token>`.

Exemplo (curl):

```powershell
curl -X POST -H "Content-Type: application/json" -d '{"username":"meu","password":"senha"}' http://127.0.0.1:5000/auth/login
```

Admin / Migração
- A interface de administração está disponível em `/admin/users` (requer login).
- Para migrar clientes de CSV/JSON para a base local, use o script:

```powershell
python controle_system/scripts/migrate_clients.py d:/PROGRAMAÇÃO-AULA/controle_system/clientes.db dados.csv
```

```
