import os
import sqlite3
import json
import secrets
import traceback
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "secret123"

DB_NAME = "data.db"

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # 🔥 permet d'utiliser formulaire["titre"]
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS formulaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT NOT NULL,
            lien_unique TEXT UNIQUE NOT NULL
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

# ================= CREATION FORMULAIRE =================
@app.route("/", methods=["GET", "POST"])
def creer_formulaire():
    try:
        if request.method == "POST":
            titre = request.form["titre"]
            lien_unique = secrets.token_urlsafe(8)

            conn = get_db()
            c = conn.cursor()

            c.execute(
                "INSERT INTO formulaires (titre, lien_unique) VALUES (?, ?)",
                (titre, lien_unique)
            )

            conn.commit()
            formulaire_id = c.lastrowid
            conn.close()

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        return render_template("creer_formulaire.html")

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR CREATE FORM: {e}"

# ================= AJOUT CHAMPS =================
@app.route("/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    try:
        conn = get_db()
        c = conn.cursor()

        # 🔥 Vérifier que le formulaire existe
        c.execute("SELECT * FROM formulaires WHERE id = ?", (formulaire_id,))
        formulaire = c.fetchone()

        if formulaire is None:
            conn.close()
            return f"Formulaire avec ID {formulaire_id} introuvable ❌"

        if request.method == "POST":
            label = request.form.get("label")
            type_champ = request.form.get("type_champ")
            options = request.form.get("options", "")
            obligatoire = 1 if request.form.get("obligatoire") else 0

            # 🔥 sécurité champ vide
            if not label or not type_champ:
                return "Label ou type manquant ❌"

            # ordre automatique
            c.execute("SELECT COUNT(*) FROM champs WHERE formulaire_id = ?", (formulaire_id,))
            ordre = c.fetchone()[0]

            c.execute('''
                INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (formulaire_id, label, type_champ, options, obligatoire, ordre))

            conn.commit()

            # 🔥 bouton TERMINER
            if "terminer" in request.form:
                c.execute("SELECT lien_unique FROM formulaires WHERE id = ?", (formulaire_id,))
                result = c.fetchone()

                if result is None:
                    conn.close()
                    return "Erreur récupération lien ❌"

                lien = result["lien_unique"]
                conn.close()

                url = url_for("afficher_formulaire", lien_unique=lien, _external=True)

                return f"""
                <h2>Formulaire créé ✅</h2>
                <p>Lien public :</p>
                <a href="{url}">{url}</a>
                """

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        # 🔥 récupération des champs
        c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", (formulaire_id,))
        champs = c.fetchall()

        conn.close()

        return render_template(
            "ajouter_champs.html",
            formulaire=formulaire,
            champs=champs,
            formulaire_id=formulaire_id
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"ERROR CHAMPS: {e}"
# ================= FORMULAIRE PUBLIC =================
@app.route("/f/<lien_unique>")
def afficher_formulaire(lien_unique):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    c.execute(
        "SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre",
        (formulaire["id"],)
    )
    champs = c.fetchall()

    conn.close()

    return render_template("form_dynamique.html", formulaire=formulaire, champs=champs)

# ================= SOUMISSION =================
@app.route("/f/<lien_unique>/submit", methods=["POST"])
def soumettre(lien_unique):
    try:
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT id FROM formulaires WHERE lien_unique = ?", (lien_unique,))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        formulaire_id = formulaire["id"]

        c.execute(
            "SELECT id, label, obligatoire FROM champs WHERE formulaire_id = ?",
            (formulaire_id,)
        )
        champs = c.fetchall()

        donnees = {}

        for champ in champs:
            champ_id = champ["id"]
            valeur = request.form.get(f"champ_{champ_id}", "")

            if champ["obligatoire"] == 1 and not valeur:
                return f"Champ '{champ['label']}' obligatoire ❌"

            donnees[str(champ_id)] = valeur

        c.execute(
            "INSERT INTO reponses (formulaire_id, donnees) VALUES (?, ?)",
            (formulaire_id, json.dumps(donnees))
        )

        conn.commit()
        conn.close()

        return "<h2>✅ Réponse enregistrée</h2>"

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR SUBMIT: {e}"

# ================= ADMIN =================
@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM formulaires")
    formulaires = c.fetchall()

    conn.close()

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
