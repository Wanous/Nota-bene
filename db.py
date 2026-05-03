"""
db.py — Couche d'accès à la base de données SQLite pour Notator.
Toutes les fonctions retournent des dicts ou des listes de dicts.
"""

import sqlite3
import os
from typing import Optional


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def get_connection(db_path: str) -> sqlite3.Connection:
    """Ouvre une connexion à la base de données et active les foreign keys."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # accès par nom de colonne
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Initialisation du schéma
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS "Classes" (
    "ID"         INTEGER PRIMARY KEY AUTOINCREMENT,
    "Name"       TEXT    NOT NULL,
    "color"      TEXT    NOT NULL DEFAULT '#67b3ff',
    "NB credits" INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS "Grades" (
    "ID"          INTEGER PRIMARY KEY AUTOINCREMENT,
    "Id_class"    INTEGER NOT NULL,
    "Name"        TEXT    NOT NULL,
    "Coefficient" REAL    NOT NULL DEFAULT 1.0,
    "Value"       REAL,
    FOREIGN KEY ("Id_class") REFERENCES "Classes"("ID") ON DELETE CASCADE
);
"""

def init_db(db_path: str) -> None:
    """Crée les tables si elles n'existent pas encore."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Matières (Classes)
# ---------------------------------------------------------------------------

def get_all_classes(db_path: str) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute('SELECT * FROM "Classes" ORDER BY "Name"').fetchall()
        return [dict(r) for r in rows]


def get_class(db_path: str, class_id: int) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            'SELECT * FROM "Classes" WHERE "ID" = ?', (class_id,)
        ).fetchone()
        return dict(row) if row else None


def create_class(db_path: str, name: str, color: str, nb_credits: int) -> int:
    """Insère une matière et retourne son ID."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'INSERT INTO "Classes" ("Name", "color", "NB credits") VALUES (?, ?, ?)',
            (name, color, nb_credits)
        )
        conn.commit()
        return cur.lastrowid


def update_class(db_path: str, class_id: int, name: str, color: str, nb_credits: int) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'UPDATE "Classes" SET "Name"=?, "color"=?, "NB credits"=? WHERE "ID"=?',
            (name, color, nb_credits, class_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_class(db_path: str, class_id: int) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute('DELETE FROM "Classes" WHERE "ID"=?', (class_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Notes (Grades)
# ---------------------------------------------------------------------------

def get_all_grades(db_path: str) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            'SELECT g.*, c."Name" as class_name, c."color" as class_color '
            'FROM "Grades" g '
            'JOIN "Classes" c ON g."Id_class" = c."ID" '
            'ORDER BY c."Name", g."Name"'
        ).fetchall()
        return [dict(r) for r in rows]


def get_grades_by_class(db_path: str, class_id: int) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            'SELECT * FROM "Grades" WHERE "Id_class"=? ORDER BY "Name"',
            (class_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_grade(db_path: str, grade_id: int) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            'SELECT g.*, c."Name" as class_name FROM "Grades" g '
            'JOIN "Classes" c ON g."Id_class" = c."ID" '
            'WHERE g."ID"=?', (grade_id,)
        ).fetchone()
        return dict(row) if row else None


def create_grade(db_path: str, id_class: int, name: str,
                 coefficient: float, value: Optional[float]) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'INSERT INTO "Grades" ("Id_class","Name","Coefficient","Value") VALUES (?,?,?,?)',
            (id_class, name, coefficient, value)
        )
        conn.commit()
        return cur.lastrowid


def update_grade(db_path: str, grade_id: int, id_class: int, name: str,
                 coefficient: float, value: Optional[float]) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'UPDATE "Grades" SET "Id_class"=?, "Name"=?, "Coefficient"=?, "Value"=? WHERE "ID"=?',
            (id_class, name, coefficient, value, grade_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_grade(db_path: str, grade_id: int) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute('DELETE FROM "Grades" WHERE "ID"=?', (grade_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Statistiques globales
# ---------------------------------------------------------------------------

def get_stats(db_path: str) -> dict:
    """
    Calcule les statistiques globales.

    Nouveaux indicateurs pondérés par crédits ECTS :
    - score_obtenu  : pourcentage réellement obtenu sur 100 %
                      = somme(moyenne_matiere * credits) / (total_credits * 20) * 100
    - moyenne_pond  : moyenne générale pondérée par les crédits (sur 20)
    - chart_credits : liste [{name, color, credits, pct}] pour le camembert 1
    - chart_scores  : liste [{name, color, score_pct, missing_pct}] pour le camembert 2
    """
    grades  = get_all_grades(db_path)
    classes = get_all_classes(db_path)

    # ---- Stats brutes (toutes notes confondues) ----
    values = [g["Value"] for g in grades if g["Value"] is not None]
    total  = len(grades)
    filled = len(values)

    if not values:
        simple_moyenne = None
        mediane = None
    else:
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mediane = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        simple_moyenne = round(sum(values) / n, 2)

    # ---- Moyenne par matière (pondérée par coefficient) ----
    class_avg: dict[int, float | None] = {}
    for c in classes:
        cid = c["ID"]
        gs  = [g for g in grades if g["Id_class"] == cid]
        filled_gs = [g for g in gs if g["Value"] is not None]
        if not filled_gs:
            class_avg[cid] = None
        else:
            total_coef = sum(g["Coefficient"] for g in filled_gs)
            class_avg[cid] = (
                sum(g["Value"] * g["Coefficient"] for g in filled_gs) / total_coef
                if total_coef else None
            )

    # ---- Graphique 1 : répartition des crédits ----
    total_credits = sum(c["NB credits"] for c in classes)
    chart_credits = []
    for c in classes:
        pct = round(c["NB credits"] / total_credits * 100, 1) if total_credits else 0
        chart_credits.append({
            "name":    c["Name"],
            "color":   c["color"],
            "credits": c["NB credits"],
            "pct":     pct,
        })

    # ---- Graphique 2 : score obtenu par matière ----
    # Chaque matière contribue à hauteur de (moy/20 * credits/total_credits * 100) %
    chart_scores = []
    score_total = 0.0
    for c in classes:
        cid  = c["ID"]
        avg  = class_avg.get(cid)
        cred = c["NB credits"]
        if avg is not None and total_credits:
            obtained = round(avg / 20 * cred / total_credits * 100, 2)
        else:
            obtained = 0.0
        score_total += obtained
        chart_scores.append({
            "name":    c["Name"],
            "color":   c["color"],
            "avg":     round(avg, 2) if avg is not None else None,
            "credits": cred,
            "obtained_pct": obtained,
        })
    missing_pct = round(max(0.0, 100.0 - score_total), 2)
    score_total = round(score_total, 2)

    # ---- Moyenne pondérée par crédits ----
    if total_credits and any(class_avg[c["ID"]] is not None for c in classes):
        num = sum(
            class_avg[c["ID"]] * c["NB credits"]
            for c in classes if class_avg[c["ID"]] is not None
        )
        den = sum(c["NB credits"] for c in classes if class_avg[c["ID"]] is not None)
        moyenne_pond = round(num / den, 2) if den else None
    else:
        moyenne_pond = None

    return {
        "moyenne":          simple_moyenne,
        "mediane":          round(mediane, 2) if mediane is not None else None,
        "minimum":          min(values) if values else None,
        "maximum":          max(values) if values else None,
        "taux_completion":  round(filled / total * 100, 1) if total else 0.0,
        "total":            total,
        "filled":           filled,
        # Nouvelles clés
        "moyenne_pond":     moyenne_pond,
        "score_obtenu":     score_total,
        "missing_pct":      missing_pct,
        "chart_credits":    chart_credits,
        "chart_scores":     chart_scores,
    }


# ---------------------------------------------------------------------------
# Utilitaires fichiers
# ---------------------------------------------------------------------------

def list_databases(folder: str = ".") -> list[str]:
    """Liste les fichiers .db présents dans le dossier donné."""
    return sorted(
        f for f in os.listdir(folder)
        if f.endswith(".db") and os.path.isfile(os.path.join(folder, f))
    )