import os
import sqlite3
import json
import secrets
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = "secret123"

DB_NAME = "data.db"

# ================= DATABASE =================
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS formulaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT,
            lien_unique TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS champs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formulaire_id INTEGER,
            label TEXT,
            type_champ TEXT,
            options TEXT,
            obligatoire INTEGER,
            ordre INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS reponses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formulaire_id INTEGER,
            donnees TEXT
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# ================= MENU =================
@app.route("/")
def home():
    return redirect(url_for("menu"))

@app.route("/menu")
def menu():
    return render_template("menu.html")

# ================= CREATION =================
@app.route("/creer", methods=["GET", "POST"])
def creer_formulaire():
    if request.method == "POST":
        titre = request.form.get("titre")
        if not titre:
            return "Titre requis ❌"

        lien_unique = secrets.token_urlsafe(8)

        db = get_db()
        c = db.cursor()

        c.execute(
            "INSERT INTO formulaires (titre, lien_unique) VALUES (?, ?)",
            (titre, lien_unique)
        )

        db.commit()
        formulaire_id = c.lastrowid

        return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

    return render_template("creer_formulaire.html")

# ================= AJOUT CHAMPS =================
@app.route("/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires WHERE id = ?", (formulaire_id,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌"

    if request.method == "POST":
        label = request.form.get("label")
        type_champ = request.form.get("type_champ")
        options = request.form.get("options", "")
        obligatoire = 1 if request.form.get("obligatoire") else 0

        if not label or not type_champ:
            return "Champ invalide ❌"

        c.execute("SELECT COUNT(*) FROM champs WHERE formulaire_id = ?", (formulaire_id,))
        ordre = c.fetchone()[0]

        c.execute('''
            INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (formulaire_id, label, type_champ, options, obligatoire, ordre))

        db.commit()

        if "terminer" in request.form:
            lien = formulaire["lien_unique"]
            url = url_for("afficher_formulaire", lien_unique=lien, _external=True)

            return f"""
            <h2>Formulaire créé ✅</h2>
            <p>Lien :</p>
            <a href="{url}">{url}</a>
            """

        return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", (formulaire_id,))
    champs = c.fetchall()

    return render_template("ajouter_champs.html", formulaire=formulaire, champs=champs, formulaire_id=formulaire_id)

# ================= FORMULAIRE PUBLIC =================
@app.route("/f/<lien_unique>")
def afficher_formulaire(lien_unique):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", (formulaire["id"],))
    champs = c.fetchall()

    return render_template("form_dynamique.html", formulaire=formulaire, champs=champs)

# ================= SOUMISSION =================
@app.route("/f/<lien_unique>/submit", methods=["POST"])
def soumettre(lien_unique):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT id FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    formulaire_id = formulaire["id"]

    c.execute("SELECT id, label, obligatoire FROM champs WHERE formulaire_id = ?", (formulaire_id,))
    champs = c.fetchall()

    data = {}

    for champ in champs:
        value = request.form.get(f"champ_{champ['id']}", "")

        if champ["obligatoire"] == 1 and not value:
            return f"Champ {champ['label']} obligatoire ❌"

        data[str(champ["id"])] = value

    c.execute(
        "INSERT INTO reponses (formulaire_id, donnees) VALUES (?, ?)",
        (formulaire_id, json.dumps(data))
    )

    db.commit()

    return "<h2>✅ Réponse enregistrée</h2>"

# ================= LISTE =================
@app.route("/liste")
def liste_formulaires():
    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires ORDER BY id DESC")
    formulaires = c.fetchall()

    return render_template("liste.html", formulaires=formulaires)

# ================= VOIR REPONSES =================
@app.route("/admin/formulaire/<int:formulaire_id>/reponses")
def voir_reponses(formulaire_id):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires WHERE id = ?", (formulaire_id,))
    formulaire = c.fetchone()

    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", (formulaire_id,))
    champs = c.fetchall()

    c.execute("SELECT * FROM reponses WHERE formulaire_id = ?", (formulaire_id,))
    reps = c.fetchall()

    reponses = []
    for r in reps:
        reponses.append(json.loads(r["donnees"]))

    return render_template("reponses.html", formulaire=formulaire, champs=champs, reponses=reponses)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
