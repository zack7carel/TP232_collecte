import os
import json
import secrets
import traceback
import psycopg2
import psycopg2.extras
import openpyxl
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, g, send_file
from werkzeug.security import generate_password_hash, check_password_hash

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
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mot_de_passe TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS formulaires (
            id SERIAL PRIMARY KEY,
            titre TEXT NOT NULL,
            lien_unique TEXT UNIQUE NOT NULL
        )
    ''')

    c.execute('''
        ALTER TABLE formulaires
        ADD COLUMN IF NOT EXISTS utilisateur_id INTEGER REFERENCES utilisateurs(id)
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

# ================= HELPERS =================
def utilisateur_connecte():
    return session.get("utilisateur_id")

def login_requis(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not utilisateur_connecte():
            return redirect(url_for("connexion"))
        return f(*args, **kwargs)
    return decorated

# ================= INSCRIPTION =================
@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    try:
        if utilisateur_connecte():
            return redirect(url_for("menu"))

        erreur = None
        if request.method == "POST":
            nom = request.form.get("nom", "").strip()
            email = request.form.get("email", "").strip().lower()
            mdp = request.form.get("mot_de_passe", "")

            if not nom or not email or not mdp:
                erreur = "Tous les champs sont obligatoires."
            elif len(mdp) < 6:
                erreur = "Le mot de passe doit contenir au moins 6 caractères."
            else:
                db = get_db()
                c = db.cursor()
                c.execute("SELECT id FROM utilisateurs WHERE email = %s", (email,))
                if c.fetchone():
                    erreur = "Un compte existe déjà avec cet email."
                else:
                    mdp_hash = generate_password_hash(mdp)
                    c.execute(
                        "INSERT INTO utilisateurs (nom, email, mot_de_passe) VALUES (%s, %s, %s) RETURNING id",
                        (nom, email, mdp_hash)
                    )
                    utilisateur_id = c.fetchone()["id"]
                    db.commit()
                    session["utilisateur_id"] = utilisateur_id
                    session["utilisateur_nom"] = nom
                    return redirect(url_for("menu"))

        return render_template("inscription.html", erreur=erreur)

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR INSCRIPTION: {e}"

# ================= CONNEXION =================
@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    try:
        if utilisateur_connecte():
            return redirect(url_for("menu"))

        erreur = None
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            mdp = request.form.get("mot_de_passe", "")

            db = get_db()
            c = db.cursor()
            c.execute("SELECT * FROM utilisateurs WHERE email = %s", (email,))
            utilisateur = c.fetchone()

            if not utilisateur or not check_password_hash(utilisateur["mot_de_passe"], mdp):
                erreur = "Email ou mot de passe incorrect."
            else:
                session["utilisateur_id"] = utilisateur["id"]
                session["utilisateur_nom"] = utilisateur["nom"]
                return redirect(url_for("menu"))

        return render_template("connexion.html", erreur=erreur)

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR CONNEXION: {e}"

# ================= DECONNEXION =================
@app.route("/deconnexion")
def deconnexion():
    session.clear()
    return redirect(url_for("connexion"))

# ================= MENU =================
@app.route("/")
@login_requis
def menu():
    return render_template("menu.html", nom=session.get("utilisateur_nom"))

# ================= LISTE DES FORMULAIRES =================
@app.route("/liste")
@login_requis
def liste_formulaires():
    try:
        db = get_db()
        c = db.cursor()
        c.execute("SELECT * FROM formulaires WHERE utilisateur_id = %s ORDER BY id DESC", (utilisateur_connecte(),))
        formulaires = c.fetchall()
        return render_template("liste.html", formulaires=formulaires)
    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR LISTE: {e}"

# ================= REPONSES D'UN FORMULAIRE =================
@app.route("/reponses/<int:formulaire_id>")
@login_requis
def voir_reponses(formulaire_id):
    try:
        db = get_db()
        c = db.cursor()

        c.execute("SELECT * FROM formulaires WHERE id = %s AND utilisateur_id = %s", (formulaire_id, utilisateur_connecte()))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        c.execute("SELECT * FROM champs WHERE formulaire_id = %s ORDER BY ordre", (formulaire_id,))
        champs_list = c.fetchall()
        champs = {str(ch["id"]): ch["label"] for ch in champs_list}

        c.execute("SELECT * FROM reponses WHERE formulaire_id = %s ORDER BY id ASC", (formulaire_id,))
        reponses = c.fetchall()

        reponses_parsed = [(i, json.loads(rep["donnees"])) for i, rep in enumerate(reponses, 1)]

        return render_template(
            "reponses.html",
            formulaire=formulaire,
            reponses=reponses,
            reponses_parsed=reponses_parsed,
            labels=list(champs.values()),
            champ_ids=list(champs.keys())
        )

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR REPONSES: {e}"

# ================= EXPORT EXCEL =================
@app.route("/reponses/<int:formulaire_id>/export")
@login_requis
def exporter_excel(formulaire_id):
    try:
        db = get_db()
        c = db.cursor()

        c.execute("SELECT * FROM formulaires WHERE id = %s AND utilisateur_id = %s", (formulaire_id, utilisateur_connecte()))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        c.execute("SELECT * FROM champs WHERE formulaire_id = %s ORDER BY ordre", (formulaire_id,))
        champs = {str(ch["id"]): ch["label"] for ch in c.fetchall()}

        c.execute("SELECT * FROM reponses WHERE formulaire_id = %s ORDER BY id ASC", (formulaire_id,))
        reponses = c.fetchall()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Réponses"
        ws.append(["#"] + list(champs.values()))

        for i, rep in enumerate(reponses, 1):
            donnees = json.loads(rep["donnees"])
            ligne = [i] + [donnees.get(champ_id, "") for champ_id in champs.keys()]
            ws.append(ligne)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        nom_fichier = f"reponses_{formulaire['titre']}.xlsx"
        return send_file(output, as_attachment=True, download_name=nom_fichier,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR EXPORT: {e}"

# ================= CREATION FORMULAIRE =================
@app.route("/creer", methods=["GET", "POST"])
@login_requis
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
                "INSERT INTO formulaires (utilisateur_id, titre, lien_unique) VALUES (%s, %s, %s) RETURNING id",
                (utilisateur_connecte(), titre, lien_unique)
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
@login_requis
def ajouter_champs(formulaire_id):
    try:
        db = get_db()
        c = db.cursor()

        c.execute("SELECT * FROM formulaires WHERE id = %s AND utilisateur_id = %s", (formulaire_id, utilisateur_connecte()))
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
                return render_template("formulaire_cree.html", url=url)

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

        return render_template("merci.html")

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR SUBMIT: {e}"

# ================= SUPPRESSION FORMULAIRE =================
@app.route("/formulaire/<int:formulaire_id>/supprimer", methods=["POST"])
@login_requis
def supprimer_formulaire(formulaire_id):
    try:
        db = get_db()
        c = db.cursor()
        c.execute("SELECT id FROM formulaires WHERE id = %s AND utilisateur_id = %s", (formulaire_id, utilisateur_connecte()))
        if not c.fetchone():
            return "Non autorisé ❌", 403
        c.execute("DELETE FROM reponses WHERE formulaire_id = %s", (formulaire_id,))
        c.execute("DELETE FROM champs WHERE formulaire_id = %s", (formulaire_id,))
        c.execute("DELETE FROM formulaires WHERE id = %s", (formulaire_id,))
        db.commit()
        return redirect(url_for("liste_formulaires"))
    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR SUPPRIMER: {e}"

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
