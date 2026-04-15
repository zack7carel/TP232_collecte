import os
import sqlite3
import json
import secrets
from flask import Flask, render_template, request, redirect, url_for, session

print("APP STARTING")
app = Flask(__name__)
app.secret_key = "secret123"

# ==================== INITIALISATION DE LA BASE ====================
def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    # Ancienne table (gardée pour compatibilité)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT,
            prenom TEXT,
            telephone TEXT,
            email TEXT,
            matricule TEXT,
            sexe TEXT
        )
    ''')
    
    # NOUVELLES TABLES pour les formulaires dynamiques
    c.execute('''
        CREATE TABLE IF NOT EXISTS formulaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT NOT NULL,
            lien_unique TEXT UNIQUE NOT NULL,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS champs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formulaire_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            type_champ TEXT NOT NULL,
            options TEXT,
            obligatoire BOOLEAN DEFAULT 0,
            ordre INTEGER DEFAULT 0,
            FOREIGN KEY (formulaire_id) REFERENCES formulaires(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS reponses_dynamiques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formulaire_id INTEGER NOT NULL,
            donnees TEXT NOT NULL,
            date_soumission TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (formulaire_id) REFERENCES formulaires(id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== ANCIEN FORMULAIRE (gardé pour l'instant) ====================
@app.route("/")
def index():
    return render_template("index.html", message="Données enregistrées avec succès ✅")

@app.route("/submit", methods=["POST"])
def submit():
    nom = request.form["nom"]
    prenom = request.form["prenom"]
    telephone = request.form["telephone"]
    email = request.form["email"]
    matricule = request.form["matricule"]
    sexe = request.form["sexe"]

    conn = sqlite3.connect('data.db')
    c = conn.cursor()

    c.execute("""
        INSERT INTO users (nom, prenom, telephone, email, matricule, sexe)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (nom, prenom, telephone, email, matricule, sexe))

    conn.commit()
    conn.close()

    return redirect(url_for('index'))

# ==================== NOUVEAU SYSTÈME DE FORMULAIRES DYNAMIQUES ====================
@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM formulaires ORDER BY date_creation DESC")
    formulaires = c.fetchall()
    conn.close()
    
    return render_template("admin_dashboard.html", formulaires=formulaires)

@app.route("/admin/creer_formulaire", methods=["GET", "POST"])
def creer_formulaire():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    if request.method == "POST":
        titre = request.form["titre"]
        lien_unique = secrets.token_urlsafe(8)  # Génère un lien unique comme "xK9pQ2R8"
        
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        c.execute("INSERT INTO formulaires (titre, lien_unique) VALUES (?, ?)", 
                  (titre, lien_unique))
        conn.commit()
        formulaire_id = c.lastrowid
        conn.close()
        
        return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))
    
    return render_template("creer_formulaire.html")

@app.route("/admin/formulaire/<int:formulaire_id>/champs", methods=["GET", "POST"])
def ajouter_champs(formulaire_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    if request.method == "POST":
        label = request.form["label"]
        type_champ = request.form["type_champ"]
        options = request.form.get("options", "")
        obligatoire = 1 if request.form.get("obligatoire") else 0
        
        # Compter les champs existants pour l'ordre
        c.execute("SELECT COUNT(*) as nb FROM champs WHERE formulaire_id = ?", 
                  (formulaire_id,))
        ordre = c.fetchone()[0]
        
        c.execute('''
            INSERT INTO champs (formulaire_id, label, type_champ, options, obligatoire, ordre)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (formulaire_id, label, type_champ, options, obligatoire, ordre))
        conn.commit()
        
        if "ajouter_autre" in request.form:
            return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))
        else:
            return redirect(url_for("admin"))
    
    # GET: afficher le formulaire d'ajout de champs
    c.execute("SELECT * FROM formulaires WHERE id = ?", (formulaire_id,))
    formulaire = c.fetchone()
    
    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", 
              (formulaire_id,))
    champs = c.fetchall()
    conn.close()
    
    return render_template("ajouter_champs.html", formulaire=formulaire, champs=champs, 
                          formulaire_id=formulaire_id)

@app.route("/admin/formulaire/<int:formulaire_id>/supprimer_champ/<int:champ_id>")
def supprimer_champ(formulaire_id, champ_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("DELETE FROM champs WHERE id = ? AND formulaire_id = ?", 
              (champ_id, formulaire_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for("ajouter_champs", formulaire_id=formulaire_id))

@app.route("/f/<lien_unique>")
def afficher_formulaire_dynamique(lien_unique):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()
    
    if not formulaire:
        return "Formulaire introuvable ❌", 404
    
    c.execute('''
        SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre
    ''', (formulaire[0],))  # formulaire[0] = id
    champs = c.fetchall()
    conn.close()
    
    return render_template("form_dynamique.html", formulaire=formulaire, champs=champs)

@app.route("/f/<lien_unique>/soumettre", methods=["POST"])
def soumettre_formulaire_dynamique(lien_unique):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM formulaires WHERE lien_unique = ?", (lien_unique,))
    formulaire = c.fetchone()
    
    if not formulaire:
        return "Formulaire introuvable ❌", 404
    
    formulaire_id = formulaire[0]
    
    # Récupérer tous les champs du formulaire pour validation
    c.execute("SELECT id, label, obligatoire FROM champs WHERE formulaire_id = ?", 
              (formulaire_id,))
    champs = c.fetchall()
    
    # Collecter les données soumises
    donnees = {}
    for champ in champs:
        champ_id = champ[0]
        valeur = request.form.get(f"champ_{champ_id}", "")
        
        # Vérifier les champs obligatoires
        if champ[2] == 1 and not valeur:
            return f"Le champ '{champ[1]}' est obligatoire ❌", 400
        
        donnees[f"champ_{champ_id}"] = valeur
    
    # Sauvegarder en JSON
    c.execute('''
        INSERT INTO reponses_dynamiques (formulaire_id, donnees)
        VALUES (?, ?)
    ''', (formulaire_id, json.dumps(donnees, ensure_ascii=False)))
    conn.commit()
    conn.close()
    
    return "✅ Données enregistrées avec succès !"

@app.route("/admin/formulaire/<int:formulaire_id>/reponses")
def voir_reponses_dynamiques(formulaire_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM formulaires WHERE id = ?", (formulaire_id,))
    formulaire = c.fetchone()
    
    c.execute('''
        SELECT * FROM reponses_dynamiques WHERE formulaire_id = ? 
        ORDER BY date_soumission DESC
    ''', (formulaire_id,))
    reponses = c.fetchall()
    
    c.execute("SELECT * FROM champs WHERE formulaire_id = ? ORDER BY ordre", 
              (formulaire_id,))
    champs = c.fetchall()
    conn.close()
    
    return render_template("voir_reponses.html", formulaire=formulaire, 
                          reponses=reponses, champs=champs)

# ==================== AUTHENTIFICATION (gardée) ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session["logged_in"] = True
            return redirect(url_for("admin"))  # Redirige vers le nouveau dashboard
        else:
            return "Identifiants incorrects ❌"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/data")
def data():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()

    return render_template("data.html", users=users)

@app.route("/test")
def test():
    return "OK DATA ROUTES WORKING"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
