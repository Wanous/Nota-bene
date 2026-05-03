"""
appdirs.py — renvoie le chemin du dossier de données applicatives selon l'OS.

Chemins utilisés :
  - Windows  : %APPDATA%\\Notator          (ex: C:\\Users\\<user>\\AppData\\Roaming\\Notator)
  - macOS    : ~/Library/Application Support/Notator
  - Linux    : $XDG_DATA_HOME/Notator      (par défaut : ~/.local/share/Notator)

Usage :
    from appdirs import get_data_dir
    folder = get_data_dir()   # crée le dossier si besoin et retourne son chemin
"""

import os
import sys
import platform


APP_NAME = "NotaBene"


def get_data_dir() -> str:
    """
    Retourne le chemin du dossier de données de l'application,
    propre à l'OS courant. Le dossier est créé s'il n'existe pas.
    """
    system = platform.system()

    if system == "Windows":
        # %APPDATA% → C:\Users\<user>\AppData\Roaming
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        data_dir = os.path.join(base, APP_NAME)

    elif system == "Darwin":
        # macOS : ~/Library/Application Support/<APP>
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        data_dir = os.path.join(base, APP_NAME)

    else:
        # Linux / BSD / autres POSIX : XDG Base Directory Specification
        # $XDG_DATA_HOME ou ~/.local/share par défaut
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        if not xdg:
            xdg = os.path.join(os.path.expanduser("~"), ".local", "share")
        data_dir = os.path.join(xdg, APP_NAME)

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


# Programme pour vérifier le résultat
if __name__ == "__main__":
    folder = get_data_dir()
    print(f"Système détecté : {platform.system()}")
    print(f"Dossier de données : {folder}")
    print(f"Existe : {os.path.isdir(folder)}")
