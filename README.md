# Controle de Caixa Online

Aplicação web pronta para deploy no **Render**, com:

- Login com usuário e senha.
- Lançamentos manuais de **entrada** e **saída**.
- Em saídas, o **motivo** é obrigatório.
- Total disponível (pode ficar positivo ou negativo).
- Aba de **contas a pagar**.
- Dashboard com lucro e despesas no mês.
- Filtro mensal e ranking de gastos por motivo.

## Tecnologias

- Python + Flask
- SQLite (arquivo local `caixa.db`)
- Gunicorn (produção)

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Acesse: `http://localhost:5000`

Usuário padrão:

- usuário: `admin`
- senha: `admin123`

> Em produção, altere via variáveis de ambiente:
> - `SECRET_KEY`
> - `ADMIN_USER`
> - `ADMIN_PASSWORD`

## Deploy no Render

### Opção 1 (Blueprint)

1. Suba este projeto para um repositório GitHub.
2. No Render, clique em **New +** > **Blueprint**.
3. Selecione o repositório.
4. O Render lerá `render.yaml` e criará o serviço automaticamente.

### Opção 2 (Web Service manual)

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- **Environment**:
  - `SECRET_KEY` = uma chave segura
  - `ADMIN_USER` = usuário desejado
  - `ADMIN_PASSWORD` = senha desejada

Pronto: após deploy, o site ficará online.
