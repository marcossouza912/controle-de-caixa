import os
import sqlite3
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "caixa.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('entrada', 'saida')),
            amount REAL NOT NULL CHECK(amount > 0),
            reason TEXT,
            description TEXT,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            reason TEXT,
            amount REAL NOT NULL CHECK(amount > 0),
            due_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pendente', 'pago')) DEFAULT 'pendente',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    existing = db.execute("SELECT id FROM users WHERE username = ?", (admin_user,)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (admin_user, generate_password_hash(admin_password)),
        )
        db.commit()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        flash("Usuário ou senha inválidos.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


def monthly_summary(month_str: str):
    db = get_db()
    income = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE type = 'entrada' AND strftime('%Y-%m', date) = ?
        """,
        (month_str,),
    ).fetchone()["total"]

    expense = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE type = 'saida' AND strftime('%Y-%m', date) = ?
        """,
        (month_str,),
    ).fetchone()["total"]

    return float(income), float(expense)


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    selected_month = request.args.get("month") or datetime.now().strftime("%Y-%m")

    income, expense = monthly_summary(selected_month)
    profit = income - expense

    balance = db.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN type = 'entrada' THEN amount ELSE -amount END), 0) AS balance
        FROM transactions
        """
    ).fetchone()["balance"]

    top_expenses = db.execute(
        """
        SELECT reason, SUM(amount) AS total
        FROM transactions
        WHERE type = 'saida'
          AND strftime('%Y-%m', date) = ?
          AND COALESCE(TRIM(reason), '') <> ''
        GROUP BY reason
        ORDER BY total DESC
        """,
        (selected_month,),
    ).fetchall()

    recent_transactions = db.execute(
        """
        SELECT id, type, amount, reason, description, date
        FROM transactions
        ORDER BY date DESC, id DESC
        LIMIT 10
        """
    ).fetchall()

    pending_accounts = db.execute(
        """
        SELECT id, title, reason, amount, due_date, status
        FROM accounts_payable
        WHERE status = 'pendente'
        ORDER BY due_date ASC
        LIMIT 10
        """
    ).fetchall()

    return render_template(
        "dashboard.html",
        selected_month=selected_month,
        income=income,
        expense=expense,
        profit=profit,
        balance=float(balance),
        top_expenses=top_expenses,
        recent_transactions=recent_transactions,
        pending_accounts=pending_accounts,
    )


@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    db = get_db()

    if request.method == "POST":
        tx_type = request.form.get("type")
        amount_raw = request.form.get("amount", "0").replace(",", ".")
        reason = request.form.get("reason", "").strip()
        description = request.form.get("description", "").strip()
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")

        try:
            amount = float(amount_raw)
        except ValueError:
            flash("Valor inválido.", "error")
            return redirect(url_for("transactions"))

        if tx_type not in {"entrada", "saida"}:
            flash("Tipo de transação inválido.", "error")
            return redirect(url_for("transactions"))

        if amount <= 0:
            flash("O valor deve ser maior que zero.", "error")
            return redirect(url_for("transactions"))

        if tx_type == "saida" and not reason:
            flash("Para saídas, o motivo é obrigatório.", "error")
            return redirect(url_for("transactions"))

        db.execute(
            """
            INSERT INTO transactions (type, amount, reason, description, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tx_type, amount, reason or None, description or None, date),
        )
        db.commit()
        flash("Transação registrada com sucesso.", "success")
        return redirect(url_for("transactions"))

    records = db.execute(
        """
        SELECT id, type, amount, reason, description, date
        FROM transactions
        ORDER BY date DESC, id DESC
        """
    ).fetchall()

    return render_template("transactions.html", records=records, today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/accounts-payable", methods=["GET", "POST"])
@login_required
def accounts_payable():
    db = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        reason = request.form.get("reason", "").strip()
        amount_raw = request.form.get("amount", "0").replace(",", ".")
        due_date = request.form.get("due_date")

        try:
            amount = float(amount_raw)
        except ValueError:
            flash("Valor da conta inválido.", "error")
            return redirect(url_for("accounts_payable"))

        if not title or not due_date:
            flash("Título e vencimento são obrigatórios.", "error")
            return redirect(url_for("accounts_payable"))

        if amount <= 0:
            flash("Valor deve ser maior que zero.", "error")
            return redirect(url_for("accounts_payable"))

        db.execute(
            """
            INSERT INTO accounts_payable (title, reason, amount, due_date)
            VALUES (?, ?, ?, ?)
            """,
            (title, reason or None, amount, due_date),
        )
        db.commit()
        flash("Conta adicionada com sucesso.", "success")
        return redirect(url_for("accounts_payable"))

    records = db.execute(
        """
        SELECT id, title, reason, amount, due_date, status
        FROM accounts_payable
        ORDER BY CASE status WHEN 'pendente' THEN 0 ELSE 1 END, due_date ASC
        """
    ).fetchall()

    return render_template("accounts_payable.html", records=records)


@app.post("/accounts-payable/<int:account_id>/toggle")
@login_required
def toggle_account_status(account_id: int):
    db = get_db()
    record = db.execute(
        "SELECT id, status FROM accounts_payable WHERE id = ?", (account_id,)
    ).fetchone()

    if not record:
        flash("Conta não encontrada.", "error")
        return redirect(url_for("accounts_payable"))

    next_status = "pago" if record["status"] == "pendente" else "pendente"
    db.execute(
        "UPDATE accounts_payable SET status = ? WHERE id = ?", (next_status, account_id)
    )
    db.commit()
    flash("Status da conta atualizado.", "success")
    return redirect(url_for("accounts_payable"))


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
