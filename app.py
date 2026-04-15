import os
print("APP STARTING")
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key="secret123"

# Créer la base de données
def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
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
    
    conn.commit()
    conn.close()

init_db()

# Afficher le formulaire
@app.route("/")
def index():
    return render_template("index.html", message="Données enregistrées avec succès ✅")

# Enregistrer les données
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

# ✅ ROUTE CORRECTEMENT PLACÉE ICI
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
    
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # identifiants simples (à améliorer plus tard)
        if username == "admin" and password == "1234":
            session["logged_in"] = True
            return redirect(url_for("data"))
        else:
            return "Identifiants incorrects ❌"

    return render_template("login.html")
    
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
    
@app.route("/test")
def test():
    return "OK DATA ROUTES WORKING"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
