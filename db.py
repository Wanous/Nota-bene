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
    "ID"       INTEGER PRIMARY KEY AUTOINCREMENT,
    "Id_class" INTEGER NOT NULL,
    "Name"     TEXT    NOT NULL,
    "Weight"   REAL    NOT NULL DEFAULT 0.0,
    "Base"     REAL    NOT NULL DEFAULT 20.0,
    "Value"    REAL,
    FOREIGN KEY ("Id_class") REFERENCES "Classes"("ID") ON DELETE CASCADE
);
"""

def init_db(db_path: str) -> None:
    """Crée les tables et applique les migrations si nécessaire."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


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
                 weight: float, value: Optional[float],
                 base: float = 20.0) -> int:
    """weight : % que représente cette éval dans la matière. base : barème de notation."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'INSERT INTO "Grades" ("Id_class","Name","Weight","Base","Value") VALUES (?,?,?,?,?)',
            (id_class, name, weight, base, value)
        )
        conn.commit()
        return cur.lastrowid


def update_grade(db_path: str, grade_id: int, id_class: int, name: str,
                 weight: float, value: Optional[float],
                 base: float = 20.0) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'UPDATE "Grades" SET "Id_class"=?, "Name"=?, "Weight"=?, "Base"=?, "Value"=? WHERE "ID"=?',
            (id_class, name, weight, base, value, grade_id)
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

    Métrique unique : Weight (pourcentage de l'éval dans la matière, 0-100).
    - pi = g["Weight"] / 100  (fraction dans la matière)
    - obtained  = sum(ni * pi)  pour les notées  (ni = valeur 0-100)
    - ungraded  = 1 - sum(pi notées)
    - lost      = sum(pi notées) - obtained
    """
    grades  = get_all_grades(db_path)
    classes = get_all_classes(db_path)

    total  = len(grades)
    filled = len([g for g in grades if g["Value"] is not None])

    # ---- Stats par matière ----
    # avg_all : moyenne sur 100 (non notés = 0), = obtained_raw * 100
    class_stats: dict[int, dict] = {}
    for c in classes:
        cid      = c["ID"]
        cgs      = [g for g in grades if g["Id_class"] == cid]
        # pi en fraction (sum peut être < 1 si % manquants)
        sum_pi_all    = sum(g["Weight"] / 100.0 for g in cgs)
        sum_pi_noted  = sum(g["Weight"] / 100.0 for g in cgs if g["Value"] is not None)
        obtained_raw  = sum(
            (g["Value"] / (g.get("Base") or 20.0)) * (g["Weight"] / 100.0)
            for g in cgs if g["Value"] is not None
        )
        ungraded_raw  = 1.0 - sum_pi_noted          # % non encore noté (fraction matière)
        lost_raw      = sum_pi_noted - obtained_raw  # % perdus

        # Moyenne sur 20 (non notés = 0) = score obtenu * 20
        avg_all = round(obtained_raw * 20, 2) if sum_pi_all > 0 else None

        class_stats[cid] = {
            "obtained_raw":  obtained_raw,
            "ungraded_raw":  max(0.0, ungraded_raw),
            "lost_raw":      max(0.0, lost_raw),
            "avg_all":       avg_all,
        }

    # ---- Répartition par crédits ECTS ----
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

    # ---- Graphique 2 : score / perdus / non notés par matière ----
    chart_scores  = []
    score_total   = 0.0
    ungraded_total= 0.0
    lost_total_cs = 0.0

    for c in classes:
        cid    = c["ID"]
        cred   = c["NB credits"]
        weight = cred / total_credits if total_credits else 0.0  # part globale
        cs     = class_stats[cid]
        cgs    = [g for g in grades if g["Id_class"] == cid]

        obtained     = round(cs["obtained_raw"]  * weight * 100, 2)
        ungraded_pct = round(cs["ungraded_raw"]  * weight * 100, 2)
        lost_pct     = round(cs["lost_raw"]      * weight * 100, 2)

        score_total    += obtained
        ungraded_total += ungraded_pct
        lost_total_cs  += lost_pct

        chart_scores.append({
            "name":         c["Name"],
            "color":        c["color"],
            "avg":          cs["avg_all"],
            "credits":      cred,
            "obtained_pct": obtained,
            "ungraded_pct": ungraded_pct,
            "lost_pct":     lost_pct,
            "grades": [
                {
                    "name":   g["Name"],
                    "weight": g["Weight"],           # % de la matière (0-100)
                    "base":   g.get("Base", 20.0) or 20.0,
                    "value":  g["Value"],            # note brute (0..base), ou None
                }
                for g in cgs
            ],
        })

    score_total    = round(score_total,    2)
    ungraded_total = round(ungraded_total, 2)
    lost_total     = round(lost_total_cs,  2)

    # Moyenne globale pondérée (non notés = 0), sur 20
    score_sur_20 = round(score_total / 100 * 20, 2)

    # Taux de complétion : % des poids déjà notés / total possible
    taux_completion = round(filled / total * 100, 1) if total else 0.0

    return {
        "taux_completion": taux_completion,
        "total":           total,
        "filled":          filled,
        "score_obtenu":    score_total,
        "score_sur_20":    score_sur_20,
        "ungraded_pct":    ungraded_total,
        "lost_pct":        lost_total,
        "chart_credits":   chart_credits,
        "chart_scores":    chart_scores,
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