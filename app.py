import os
import json
import secrets
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "secret123"

# ================= DATABASE =================
def get_db():
    conn = psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )
    conn.autocommit = True
    return conn

# ================= INIT DB =================
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS formulaires (
            id SERIAL PRIMARY KEY,
            titre TEXT NOT NULL,
            lien_unique TEXT UNIQUE NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS champs (
            id SERIAL PRIMARY KEY,
            formulaire_id INTEGER,
            label TEXT,
            type_champ TEXT,
            options TEXT,
            obligatoire INTEGER,
            ordre INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reponses (
            id SERIAL PRIMARY KEY,
            formulaire_id INTEGER,
            donnees TEXT
        )
    """)

    conn.close()

init_db()

# ================= MENU =================
@app.route("/")
def home():
    return redirect(url_for("menu"))

@app.route("/menu")
def menu():
    return render_template("menu.html")

# ================= CREER FORMULAIRE =================
@app.route("/creer", methods=["GET", "POST"])
def creer_formulaire():
    try:
        if request.method == "POST":
            titre = request.form.get("titre")

            if not titre:
                return "Titre requis ❌"

            lien_unique = secrets.token_urlsafe(8)

            conn = get_db()
            c = conn.cursor()

            c.execute(
                "INSERT INTO formulaires (titre, lien_unique) VALUES (%s, %s)",
                (titre, lien_unique)
            )

            c.execute(
                "SELECT id FROM formulaires WHERE lien_unique=%s",
                (lien_unique,)
            )

            formulaire_id = c.fetchone()["id"]
            conn.close()

            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        return render_template("creer_formulaire.html")

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR CREATE: {e}"

# ================= AJOUT CHAMPS =================
@app.route("/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    try:
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT * FROM formulaires WHERE id=%s", (formulaire_id,))
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

            # ✅ CORRECTION COUNT
            c.execute(
                "SELECT COUNT(*) AS total FROM champs WHERE formulaire_id=%s",
                (formulaire_id,)
            )
            ordre = c.fetchone()["total"]

            c.execute("""
                INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (formulaire_id, label, type_champ, options, obligatoire, ordre))

            conn.commit()

            if "terminer" in request.form:
                url = url_for(
                    "afficher_formulaire",
                    lien_unique=formulaire["lien_unique"],
                    _external=True
                )

                conn.close()

                return f"""
                <h2>Formulaire créé ✅</h2>
                <a href="{url}">{url}</a>
                """

            conn.close()
            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

        c.execute(
            "SELECT * FROM champs WHERE formulaire_id=%s ORDER BY ordre",
            (formulaire_id,)
        )
        champs = c.fetchall()

        conn.close()

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
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM formulaires WHERE lien_unique=%s", (lien_unique,))
    formulaire = c.fetchone()

    if not formulaire:
        return "Formulaire introuvable ❌", 404

    c.execute(
        "SELECT * FROM champs WHERE formulaire_id=%s ORDER BY ordre",
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

        c.execute("SELECT id FROM formulaires WHERE lien_unique=%s", (lien_unique,))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        formulaire_id = formulaire["id"]

        c.execute("SELECT * FROM champs WHERE formulaire_id=%s", (formulaire_id,))
        champs = c.fetchall()

        data = {}

        for champ in champs:
            value = request.form.get(f"champ_{champ['id']}", "")

            if champ["obligatoire"] == 1 and not value:
                return f"Champ {champ['label']} obligatoire ❌"

            data[str(champ["id"])] = value

        c.execute(
            "INSERT INTO reponses (formulaire_id, donnees) VALUES (%s, %s)",
            (formulaire_id, json.dumps(data))
        )

        conn.close()

        return "<h2>✅ Réponse enregistrée</h2>"

    except Exception as e:
        print(traceback.format_exc())
        return f"ERROR SUBMIT: {e}"

# ================= LISTE =================
@app.route("/liste")
def liste():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM formulaires ORDER BY id DESC")
    formulaires = c.fetchall()

    conn.close()

    return render_template("liste.html", formulaires=formulaires)

# ================= REPONSES =================
@app.route("/admin/formulaire/<int:formulaire_id>/reponses")
def reponses(formulaire_id):
    try:
        conn = get_db()
        c = conn.cursor()

        # 🔥 formulaire
        c.execute("SELECT * FROM formulaires WHERE id=%s", (formulaire_id,))
        formulaire = c.fetchone()

        if not formulaire:
            return "Formulaire introuvable ❌", 404

        # 🔥 champs
        c.execute(
            "SELECT * FROM champs WHERE formulaire_id=%s ORDER BY ordre",
            (formulaire_id,)
        )
        champs = c.fetchall()

        # 🔥 réponses (SAFE MODE)
        c.execute(
            "SELECT donnees FROM reponses WHERE formulaire_id=%s ORDER BY id DESC",
            (formulaire_id,)
        )
        rows = c.fetchall()

        reponses = []

        for row in rows:
            try:
                if row and row["donnees"]:
                    reponses.append(json.loads(row["donnees"]))
                else:
                    reponses.append({})
            except Exception:
                reponses.append({})

        conn.close()

        return render_template(
            "reponses.html",
            formulaire=formulaire,
            champs=champs,
            reponses=reponses
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"ERROR REPONSES: {e}"
# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
