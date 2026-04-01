"""
memory.py — Gestión de memoria de posts publicados.

Lee y escribe en posts_publicados.json para evitar temas repetidos
y mantener un historial de publicaciones.
"""

import json
import os
from datetime import datetime, timedelta

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "posts_publicados.json")


def _leer_memoria() -> list[dict]:
    """Lee el archivo JSON de memoria. Devuelve lista vacía si no existe."""
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _escribir_memoria(datos: list[dict]) -> None:
    """Escribe la lista completa de posts en el archivo JSON."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def guardar_post(post: dict) -> None:
    """
    Añade una entrada al historial de posts.

    Estructura esperada:
    {
        "fecha": "2026-03-25",
        "tema": "...",
        "formato": "storytelling" o "tecnico",
        "puntuacion_editor": 8,
        "publicado": True
    }
    """
    datos = _leer_memoria()
    datos.append(post)
    _escribir_memoria(datos)


def temas_recientes(semanas: int = 4) -> list[dict]:
    """Devuelve los posts de las últimas N semanas."""
    datos = _leer_memoria()
    limite = datetime.now() - timedelta(weeks=semanas)
    recientes = []
    for post in datos:
        try:
            fecha = datetime.strptime(post["fecha"], "%Y-%m-%d")
            if fecha >= limite:
                recientes.append(post)
        except (KeyError, ValueError):
            continue
    return recientes


def tema_repetido(tema_nuevo: str) -> tuple[bool, list[str]]:
    """
    Comprueba si el tema es similar a algo publicado en las últimas 4 semanas.

    Devuelve (True/False, lista de temas similares encontrados).
    Usa comparación simple por palabras clave compartidas.
    """
    recientes = temas_recientes()
    if not recientes:
        return False, []

    palabras_nuevo = set(tema_nuevo.lower().split())
    # Eliminar palabras muy comunes
    stopwords = {"de", "la", "el", "en", "un", "una", "los", "las", "y", "a",
                 "para", "con", "que", "del", "al", "por", "es", "se", "su"}
    palabras_nuevo -= stopwords

    temas_similares = []
    for post in recientes:
        palabras_post = set(post["tema"].lower().split()) - stopwords
        coincidencias = palabras_nuevo & palabras_post
        # Si comparten más del 40% de las palabras significativas, es similar
        if palabras_nuevo and len(coincidencias) / len(palabras_nuevo) > 0.4:
            temas_similares.append(post["tema"])

    return len(temas_similares) > 0, temas_similares


# ══════════════════════════════════════════════════════════════
# INSTRUCCIONES
# ══════════════════════════════════════════════════════════════
# Este módulo gestiona el archivo posts_publicados.json.
#
# Uso:
#   from memory import guardar_post, temas_recientes, tema_repetido
#
#   # Comprobar si un tema ya se trató
#   repetido, similares = tema_repetido("Agentes de IA con CrewAI")
#
#   # Guardar un post publicado
#   guardar_post({
#       "fecha": "2026-04-01",
#       "tema": "Agentes de IA con CrewAI",
#       "formato": "tecnico",
#       "puntuacion_editor": 8,
#       "publicado": True
#   })
#
#   # Ver posts recientes
#   recientes = temas_recientes(semanas=4)
# ══════════════════════════════════════════════════════════════
