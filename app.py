import os
import sqlite3
import time

from flask import Flask, render_template, request, redirect, url_for, session


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "site.db")

SENHA_DONO = "000111"
TEMPO_BLOQUEIO = 24 * 60 * 60

app = Flask(__name__)
app.secret_key = "cauan01-chave-secreta"


def banco():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def iniciar_banco():
    conn = banco()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS vagas (
            cargo TEXT PRIMARY KEY,
            quantidade INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            idff TEXT NOT NULL,
            cargo TEXT NOT NULL,
            contato TEXT NOT NULL,
            meio TEXT NOT NULL,
            criado INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bloqueios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            contato TEXT NOT NULL,
            liberado_em INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS aceitos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            idff TEXT NOT NULL,
            cargo TEXT NOT NULL,
            contato TEXT NOT NULL,
            meio TEXT NOT NULL,
            criado INTEGER NOT NULL
        )
    """)

    for cargo in ["DIVULGADOR", "VIP PREMIUM", "ADM"]:
        conn.execute(
            """
            INSERT OR IGNORE INTO vagas
            (cargo, quantidade)
            VALUES (?, 0)
            """,
            (cargo,)
        )

    conn.commit()
    conn.close()


def limpar_bloqueios():
    agora = int(time.time())

    conn = banco()

    conn.execute(
        """
        DELETE FROM bloqueios
        WHERE liberado_em <= ?
        """,
        (agora,)
    )

    conn.commit()
    conn.close()


@app.route("/")
def inicio():
    limpar_bloqueios()

    conn = banco()

    vagas = {}

    for linha in conn.execute(
        "SELECT cargo, quantidade FROM vagas"
    ):
        vagas[linha["cargo"]] = linha["quantidade"]

    conn.close()

    return render_template(
        "index.html",
        vagas=vagas,
        mensagem=request.args.get("mensagem")
    )


@app.route("/pedido", methods=["POST"])
def pedido():

    limpar_bloqueios()

    nome = request.form.get("nome", "").strip()
    idff = request.form.get("idff", "").strip()
    cargo = request.form.get("cargo", "").strip()
    contato = request.form.get("contato", "").strip()
    meio = request.form.get("meio", "").strip()

    if not all([nome, idff, cargo, contato, meio]):
        return redirect(url_for("inicio", mensagem="preencha"))

    if cargo not in ["DIVULGADOR", "VIP PREMIUM", "ADM"]:
        return redirect(url_for("inicio", mensagem="opcao"))

    if meio not in ["WhatsApp", "Instagram"]:
        return redirect(url_for("inicio", mensagem="contato"))

    conn = banco()

    bloqueio = conn.execute(
        """
        SELECT *
        FROM bloqueios
        WHERE contato = ?
        """,
        (contato,)
    ).fetchone()

    if bloqueio:
        if bloqueio["liberado_em"] > int(time.time()):
            conn.close()
            return redirect(url_for("inicio", mensagem="24h"))

        conn.execute(
            "DELETE FROM bloqueios WHERE id = ?",
            (bloqueio["id"],)
        )

    vaga = conn.execute(
        """
        SELECT quantidade
        FROM vagas
        WHERE cargo = ?
        """,
        (cargo,)
    ).fetchone()

    if vaga is None or vaga["quantidade"] <= 0:
        conn.close()
        return redirect(url_for("inicio", mensagem="semvaga"))

    agora = int(time.time())

    conn.execute(
        """
        INSERT INTO pedidos
        (nome, idff, cargo, contato, meio, criado)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (nome, idff, cargo, contato, meio, agora)
    )

    conn.execute(
        """
        UPDATE vagas
        SET quantidade = quantidade - 1
        WHERE cargo = ?
        AND quantidade > 0
        """,
        (cargo,)
    )

    conn.execute(
        """
        INSERT INTO bloqueios
        (nome, contato, liberado_em)
        VALUES (?, ?, ?)
        """,
        (nome, contato, agora + TEMPO_BLOQUEIO)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("inicio", mensagem="sucesso"))


@app.route("/login", methods=["POST"])
def login():

    senha = request.form.get("senha", "")

    if senha == SENHA_DONO:
        session["dono"] = True
        return redirect(url_for("area_dono"))

    return redirect(url_for("inicio", mensagem="senha"))


@app.route("/dono")
def area_dono():

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    limpar_bloqueios()

    conn = banco()

    pedidos = conn.execute(
        "SELECT * FROM pedidos ORDER BY id DESC"
    ).fetchall()

    bloqueios = conn.execute(
        "SELECT * FROM bloqueios ORDER BY id DESC"
    ).fetchall()

    aceitos = conn.execute(
        "SELECT * FROM aceitos ORDER BY id DESC"
    ).fetchall()

    vagas = {}

    for linha in conn.execute(
        "SELECT cargo, quantidade FROM vagas"
    ):
        vagas[linha["cargo"]] = linha["quantidade"]

    conn.close()

    return render_template(
        "dono.html",
        pedidos=pedidos,
        bloqueios=bloqueios,
        aceitos=aceitos,
        vagas=vagas,
        agora=int(time.time())
    )


@app.route("/sair")
def sair():

    session.clear()

    return redirect(url_for("inicio"))


@app.route("/aceitar/<int:id>", methods=["POST"])
def aceitar(id):

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    conn = banco()

    pedido = conn.execute(
        "SELECT * FROM pedidos WHERE id = ?",
        (id,)
    ).fetchone()

    if pedido:

        conn.execute(
            """
            INSERT INTO aceitos
            (nome, idff, cargo, contato, meio, criado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pedido["nome"],
                pedido["idff"],
                pedido["cargo"],
                pedido["contato"],
                pedido["meio"],
                pedido["criado"]
            )
        )

        conn.execute(
            "DELETE FROM pedidos WHERE id = ?",
            (id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("area_dono"))


@app.route("/recusar/<int:id>", methods=["POST"])
def recusar(id):

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    conn = banco()

    pedido = conn.execute(
        "SELECT * FROM pedidos WHERE id = ?",
        (id,)
    ).fetchone()

    if pedido:

        conn.execute(
            """
            UPDATE vagas
            SET quantidade = quantidade + 1
            WHERE cargo = ?
            """,
            (pedido["cargo"],)
        )

        conn.execute(
            "DELETE FROM pedidos WHERE id = ?",
            (id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("area_dono"))


@app.route("/liberar/<int:id>", methods=["POST"])
def liberar(id):

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    conn = banco()

    conn.execute(
        "DELETE FROM bloqueios WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("area_dono"))


@app.route("/deletar-aceito/<int:id>", methods=["POST"])
def deletar_aceito(id):

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    conn = banco()

    conn.execute(
        "DELETE FROM aceitos WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("area_dono"))


@app.route("/vagas", methods=["POST"])
def atualizar_vagas():

    if not session.get("dono"):
        return redirect(url_for("inicio"))

    conn = banco()

    campos = {
        "DIVULGADOR": "divulgador",
        "VIP PREMIUM": "vip_premium",
        "ADM": "adm"
    }

    for cargo, campo in campos.items():

        valor = request.form.get(campo)

        try:
            quantidade = int(valor)
        except (ValueError, TypeError):
            continue

        if quantidade < 0:
            quantidade = 0

        conn.execute(
            """
            UPDATE vagas
            SET quantidade = ?
            WHERE cargo = ?
            """,
            (quantidade, cargo)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("area_dono"))


iniciar_banco()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False
    )
