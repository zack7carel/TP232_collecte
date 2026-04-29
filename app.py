import os
import json
import secrets
import traceback
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret123")

DATABASE_URL = os.environ.get("DATABASE_URL")

# ================= DATABASE =================
def get_db():
    if "db" not in g:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS formulaires (
            id SERIAL PRIMARY KEY,
            titre TEXT NOT NULL,
            lien_unique TEXT UNIQUE NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS champs (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            formulaire_id INTEGER,
            donnees TEXT
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# ================= CREATION FORMULAIRE =================
@app.route("/", methods=["GET", "POST"])
def creer_formulaire():
    try:
        if request.method == "POST":
            titre = request.form.get("titre")

            if not titre:
                return "Titre requis ❌"

            lien_unique = secrets.token_urlsafe(8)

            db = get_db()
            c = db.cursor()

            c.execute(
                "INSERT INTO formulaires (titre, lien_unique) VALUES (%s, %s) RETURNING id",
                (titre, lien_unique)
            )
            formulaire_id = c.fetchone()["id"]
            db.commit()

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        return render_template("creer_formulaire.html")

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR CREATE FORM: {e}"

# ================= AJOUT CHAMPS =================
@app.route("/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    try:
        db = get_db()
        c = db.cursor()

        c.execute("SELECT * FROM formulaires WHERE id = %s", (formulaire_id,))
        formulaire = c.fetchone()

        if formulaire is None:
            return "Formulaire introuvable ❌"

        if request.method == "POST":
            label = request.form.get("label")
            type_champ = request.form.get("type_champ")
            options = request.form.get("options", "")
            obligatoire = 1 if request.form.get("obligatoire") else 0

            if not label or not type_champ:
                return "Champ invalide ❌"

            c.execute("SELECT COUNT(*) as cnt FROM champs WHERE formulaire_id = %s", (formulaire_id,))
            ordre = c.fetchone()["cnt"]

            c.execute('''
                INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (formulaire_id, label, type_champ, options, obligatoire, ordre))

            db.commit()

            if "terminer" in request.form:
                lien = formulaire["lien_unique"]
                url = url_for("afficher_formulaire", lien_unique=lien, _external=True)
                return f"""
                <h2>Formulaire créé ✅</h2>
                <a href="{url}">{url}</a>
                """

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        c.execute("SELECT * FROM champs WHERE formulaire_id = %s ORDER BY ordre", (formulaire_id,))
        champs = c.fetchall()

        return render_template(
            "ajouter_champs.html",
            formulaire=formulaire,
            champs=champs,
            formulaire_id=formulaire_id
        )

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR CHAMPS: {e}"

# ================= FORMULAIRE PUBLIC =================
@app.route("/f/<lien_unique>")
def afficher_formulaire(lien_unique):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires WHERE lien_unique = %s", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    c.execute("SELECT * FROM champs WHERE formulaire_id = %s ORDER BY ordre", (formulaire["id"],))
    champs = c.fetchall()

    return render_template("form_dynamique.html", formulaire=formulaire, champs=champs)

# ================= SOUMISSION =================
@app.route("/f/<lien_unique>/submit", methods=["POST"])
def soumettre(lien_unique):
    try:
        db = get_db()
        c = db.cursor()

        c.execute("SELECT id FROM formulaires WHERE lien_unique = %s", (lien_unique,))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        formulaire_id = formulaire["id"]

        c.execute("SELECT id, label, obligatoire FROM champs WHERE formulaire_id = %s", (formulaire_id,))
        champs = c.fetchall()

        donnees = {}

        for champ in champs:
            champ_id = champ["id"]
            valeur = request.form.get(f"champ_{champ_id}", "")

            if champ["obligatoire"] == 1 and not valeur:
                return f"Champ '{champ['label']}' obligatoire ❌"

            donnees[str(champ_id)] = valeur

        c.execute(
            "INSERT INTO reponses (formulaire_id, donnees) VALUES (%s, %s)",
            (formulaire_id, json.dumps(donnees))
        )

        db.commit()

        return "<h2>✅ Réponse enregistrée</h2>"

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR SUBMIT: {e}"

# ================= ADMIN =================
@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    c = db.cursor()

    c.execute("SELECT * FROM formulaires")
    formulaires = c.fetchall()

    return render_template("admin_dashboard.html", formulaires=formulaires)

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "1234":
            session["logged_in"] = True
            return redirect(url_for("admin"))
        return "Erreur login ❌"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
