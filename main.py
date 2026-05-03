"""
main.py — Serveur Flask pour Notator.
Lance avec :  python main.py
"""

import os
import re
import threading
import webbrowser
from flask import (
    Flask, render_template, redirect, url_for,
    request, jsonify, session, abort, send_from_directory
)
import db as database
from appdirs import get_data_dir

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(APP_DIR, "templates"),
            static_folder=APP_DIR,
            static_url_path="")
app.secret_key = os.environ.get("NOTATOR_SECRET", "notator-dev-secret")

# Dossier dans lequel on stocke les bases de données (dépend de l'OS)
DB_FOLDER = get_data_dir()


# ============================================================
# Helpers
# ============================================================

def current_db() -> str | None:
    """Retourne le chemin absolu de la DB active, ou None."""
    name = session.get("db_name")
    if not name:
        return None
    return os.path.join(DB_FOLDER, name)


def require_db():
    """Redirige vers le menu si aucune DB n'est sélectionnée."""
    path = current_db()
    if not path or not os.path.exists(path):
        session.pop("db_name", None)
        return redirect(url_for("menu"))
    return None


# ============================================================
# Menu principal — sélection / création de base de données
# ============================================================

@app.route("/")
def menu():
    dbs = database.list_databases(DB_FOLDER)
    return render_template("menu.html", databases=dbs)


@app.route("/select", methods=["POST"])
def select_db():
    name = request.form.get("db_name", "").strip()
    path = os.path.join(DB_FOLDER, name)
    if not name or not os.path.exists(path):
        abort(400, "Base de données introuvable.")
    session["db_name"] = name
    return redirect(url_for("index"))


@app.route("/delete", methods=["POST"])
def delete_db():
    name = request.form.get("db_name", "").strip()
    path = os.path.join(DB_FOLDER, name)
    if not name or not os.path.exists(path):
        abort(400, "Base de données introuvable.")
    # Si la base supprimée est celle en session, on la désélectionne
    if session.get("db_name") == name:
        session.pop("db_name", None)
    os.remove(path)
    return redirect(url_for("menu"))


@app.route("/rename", methods=["POST"])
def rename_db():
    old_name = request.form.get("old_name", "").strip()
    raw_new  = request.form.get("new_name", "").strip()
    if not old_name or not raw_new:
        abort(400, "Nom manquant.")
    new_name = re.sub(r"[^\w\-]", "_", raw_new)
    if not new_name.endswith(".db"):
        new_name += ".db"
    old_path = os.path.join(DB_FOLDER, old_name)
    new_path = os.path.join(DB_FOLDER, new_name)
    if not os.path.exists(old_path):
        abort(400, "Base de données introuvable.")
    if os.path.exists(new_path):
        abort(400, "Une base avec ce nom existe déjà.")
    os.rename(old_path, new_path)
    # Mise à jour de la session si c'était la base active
    if session.get("db_name") == old_name:
        session["db_name"] = new_name
    return redirect(url_for("menu"))


@app.route("/create", methods=["POST"])
def create_db():
    raw = request.form.get("new_db_name", "").strip()
    if not raw:
        abort(400, "Nom manquant.")
    # On s'assure que le nom est sûr (alphanum + tirets/underscores)
    name = re.sub(r"[^\w\-]", "_", raw)
    if not name.endswith(".db"):
        name += ".db"
    path = os.path.join(DB_FOLDER, name)
    database.init_db(path)
    session["db_name"] = name
    return redirect(url_for("index"))


# ============================================================
# Page principale (dashboard)
# ============================================================

@app.route("/app")
def index():
    redir = require_db()
    if redir:
        return redir
    db = current_db()
    stats   = database.get_stats(db)
    classes = database.get_all_classes(db)
    grades  = database.get_all_grades(db)
    return render_template(
        "index.html",
        db_name=session["db_name"],
        stats=stats,
        classes=classes,
        grades=grades
    )


@app.route("/logout")
def logout():
    session.pop("db_name", None)
    return redirect(url_for("menu"))


# ============================================================
# API — Matières (Classes)
# ============================================================

@app.route("/api/classes", methods=["GET"])
def api_get_classes():
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    return jsonify(database.get_all_classes(current_db()))


@app.route("/api/classes", methods=["POST"])
def api_create_class():
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    data = request.get_json(force=True)
    try:
        cid = database.create_class(
            current_db(),
            name=data["name"],
            color=data.get("color", "#67b3ff"),
            nb_credits=int(data.get("nb_credits", 0))
        )
        return jsonify({"id": cid}), 201
    except (KeyError, ValueError) as e:
        abort(400, str(e))


@app.route("/api/classes/<int:class_id>", methods=["GET"])
def api_get_class(class_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    c = database.get_class(current_db(), class_id)
    if not c:
        abort(404)
    return jsonify(c)


@app.route("/api/classes/<int:class_id>", methods=["PUT"])
def api_update_class(class_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    data = request.get_json(force=True)
    ok = database.update_class(
        current_db(), class_id,
        name=data["name"],
        color=data.get("color", "#67b3ff"),
        nb_credits=int(data.get("nb_credits", 0))
    )
    if not ok:
        abort(404)
    return jsonify({"updated": class_id})


@app.route("/api/classes/<int:class_id>", methods=["DELETE"])
def api_delete_class(class_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    ok = database.delete_class(current_db(), class_id)
    if not ok:
        abort(404)
    return jsonify({"deleted": class_id})


# ============================================================
# API — Notes (Grades)
# ============================================================

@app.route("/api/grades", methods=["GET"])
def api_get_grades():
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    class_id = request.args.get("class_id", type=int)
    if class_id:
        return jsonify(database.get_grades_by_class(current_db(), class_id))
    return jsonify(database.get_all_grades(current_db()))


@app.route("/api/grades", methods=["POST"])
def api_create_grade():
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    data = request.get_json(force=True)
    try:
        raw_value = data.get("value")
        value = float(raw_value) if raw_value not in (None, "", "null") else None
        gid = database.create_grade(
            current_db(),
            id_class=int(data["id_class"]),
            name=data["name"],
            coefficient=float(data.get("coefficient", 1.0)),
            value=value,
            base=float(data.get("base", 20.0))
        )
        return jsonify({"id": gid}), 201
    except (KeyError, ValueError) as e:
        abort(400, str(e))


@app.route("/api/grades/<int:grade_id>", methods=["GET"])
def api_get_grade(grade_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    g = database.get_grade(current_db(), grade_id)
    if not g:
        abort(404)
    return jsonify(g)


@app.route("/api/grades/<int:grade_id>", methods=["PUT"])
def api_update_grade(grade_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    data = request.get_json(force=True)
    try:
        raw_value = data.get("value")
        value = float(raw_value) if raw_value not in (None, "", "null") else None
        ok = database.update_grade(
            current_db(), grade_id,
            id_class=int(data["id_class"]),
            name=data["name"],
            coefficient=float(data.get("coefficient", 1.0)),
            value=value,
            base=float(data.get("base", 20.0))
        )
    except (KeyError, ValueError) as e:
        abort(400, str(e))
    if not ok:
        abort(404)
    return jsonify({"updated": grade_id})


@app.route("/api/grades/<int:grade_id>", methods=["DELETE"])
def api_delete_grade(grade_id):
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    ok = database.delete_grade(current_db(), grade_id)
    if not ok:
        abort(404)
    return jsonify({"deleted": grade_id})


# ============================================================
# API — Stats
# ============================================================

@app.route("/api/stats", methods=["GET"])
def api_stats():
    redir = require_db()
    if redir:
        return jsonify({"error": "No database selected"}), 400
    return jsonify(database.get_stats(current_db()))


# ============================================================
# Fichiers statiques (style.css, script.js…)
# ============================================================

# Les fichiers statiques (style.css, script.js…) sont servis automatiquement
# par Flask depuis APP_DIR grâce à static_folder + static_url_path=""


# ============================================================
# Lancement
# ============================================================

if __name__ == "__main__":
    PORT = 5000
    URL  = f"http://127.0.0.1:{PORT}"

    # Ouvre le navigateur une fois que Flask est prêt (après 1 s)
    def _open_browser():
        webbrowser.open(URL)

    timer = threading.Timer(1.0, _open_browser)
    timer.daemon = True
    timer.start()

    print(f"  Notator → {URL}")
    print(f"  Bases de données → {DB_FOLDER}")
    app.run(debug=False, port=PORT)