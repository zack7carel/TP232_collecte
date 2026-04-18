import os
import sqlite3
import json
import secrets
import traceback
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "secret123"

# ================= DATABASE =================
def get_db():
    return sqlite3.connect('data.db')

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

# ================= PAGE D'ACCUEIL = CREATION =================
@app.route("/", methods=["GET", "POST"])
def creer_formulaire():
    try:
        if request.method == "POST":
            titre = request.form["titre"]
            lien_unique = secrets.token_urlsafe(8)

            conn = get_db()
            c = conn.cursor()

            c.execute("INSERT INTO formulaires (titre, lien_unique) VALUES (?, ?)",
                      (titre, lien_unique))

            conn.commit()
            formulaire_id = c.lastrowid
            conn.close()

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        return render_template("creer_formulaire.html")

    except Exception as e:
        return f"ERREUR: {str(e)}"

# ================= AJOUT CHAMPS =================
@app.route("/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        label = request.form["label"]
        type_champ = request.form["type_champ"]
        options = request.form.get("options", "")
        obligatoire = 1 if request.form.get("obligatoire") else 0

        c.execute("SELECT COUNT(*) FROM champs WHERE formulaire_id = ?", (formulaire_id,))
        ordre = c.fetchone()[0]

        c.execute('''
            INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (formulaire_id, label, type_champ, options, obligatoire, ordre))

        conn.commit()

        if "terminer" in request.form:
            c.execute("SELECT lien_unique FROM formulaires WHERE id = ?", (formulaire_id,))
            lien = c.fetchone()[0]
            conn.close()

            url = url_for("afficher_formulaire", lien_unique=lien, _external=True)

            return f"""
            <h2>Formulaire créé ✅</h2>
            <p>Lien public :</p>
            <a href="{url}">{url}</a>
            """

        return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

    c.execute("SELECT * FROM champs WHERE formulaire_id = ?", (formulaire_id,))
    champs = c.fetchall()
    conn.close()

    return render_template("ajouter_champs.html", champs=champs, formulaire_id=formulaire_id)

# ================= FORMULAIRE PUBLIC =================
@app.route("/f/<lien_unique>")
def afficher_formulaire(lien_unique):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre",
              (formulaire[0],))
    champs = c.fetchall()

    conn.close()

    return render_template("form_dynamique.html", formulaire=formulaire, champs=champs)

# ================= SOUMISSION =================
@app.route("/f/<lien_unique>/submit", methods=["POST"])
def soumettre(lien_unique):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    formulaire_id = formulaire[0]

    c.execute("SELECT id, label, obligatoire FROM champs WHERE formulaire_id = ?",
              (formulaire_id,))
    champs = c.fetchall()

    donnees = {}

    for champ in champs:
        champ_id = champ[0]
        valeur = request.form.get(f"champ_{champ_id}", "")

        if champ[2] == 1 and not valeur:
            return f"Champ '{champ[1]}' obligatoire ❌"

        donnees[str(champ_id)] = valeur

    c.execute("INSERT INTO reponses (formulaire_id, donnees) VALUES (?, ?)",
              (formulaire_id, json.dumps(donnees)))

    conn.commit()
    conn.close()

    return "<h2>✅ Réponse enregistrée</h2>"

# ================= ADMIN (CONSULTATION UNIQUEMENT) =================
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
        return "Erreur ❌"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
