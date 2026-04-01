"""
tasks.py — Definición de tareas CrewAI para el flujo de generación.

Cada función crea una Task asociada a su agente correspondiente.
"""

from crewai import Task, Agent


def tarea_investigar(agente: Agent, tema: str) -> Task:
    """Tarea para el Investigador: buscar contexto sobre el tema."""
    return Task(
        description=(
            f"Investiga el siguiente tema para un post de LinkedIn: '{tema}'.\n\n"
            "Devuelve:\n"
            "1. Contexto actual del tema (qué está pasando ahora en la industria)\n"
            "2. 3-5 datos o hechos concretos y verificables\n"
            "3. El ángulo más interesante para un post de LinkedIn B2B\n"
            "4. Tono recomendado para la audiencia\n\n"
            "Si no encuentras información suficiente, indícalo claramente."
        ),
        expected_output=(
            "Un informe con contexto actual, datos verificables, "
            "ángulo recomendado y tono sugerido."
        ),
        agent=agente,
    )


def tarea_proponer_temas(agente: Agent) -> Task:
    """Tarea para el Investigador: proponer 3 temas de la semana (modo automático)."""
    return Task(
        description=(
            "Propón 3 temas relevantes de esta semana en el ámbito de "
            "IA, automatización, agentes de IA y tecnología.\n\n"
            "Los temas deben ser:\n"
            "- Actuales y relevantes para profesionales B2B\n"
            "- Adecuados para el perfil de Vanessa Larrosa "
            "(Directora de Automatizaciones y Agentes en IA Experience)\n"
            "- Variados entre sí\n\n"
            "Devuelve exactamente 3 temas, cada uno en una línea, "
            "numerados del 1 al 3. Solo el título del tema, sin explicación."
        ),
        expected_output="3 temas numerados, uno por línea.",
        agent=agente,
    )


def tarea_redactar(agente: Agent, tema: str, formato: str,
                   contexto_investigacion: str,
                   feedback_editor: str = "") -> Task:
    """Tarea para el Redactor: generar el post de LinkedIn."""
    instrucciones_extra = ""
    if feedback_editor:
        instrucciones_extra = (
            f"\n\nATENCIÓN: El editor ha revisado una versión anterior y ha dado "
            f"este feedback. Debes incorporar estas mejoras:\n{feedback_editor}"
        )

    return Task(
        description=(
            f"Escribe un post de LinkedIn sobre: '{tema}'\n"
            f"Formato: {formato}\n\n"
            f"Contexto de la investigación:\n{contexto_investigacion}\n\n"
            f"Recuerda las reglas:\n"
            f"- Máximo 150 palabras\n"
            f"- Sin emojis excesivos (máximo 2-3)\n"
            f"- Sin frases vacías de motivación\n"
            f"- Que suene a Vanessa, no a IA\n"
            f"- Primera línea es lo más importante"
            f"{instrucciones_extra}"
        ),
        expected_output=f"Un post de LinkedIn en formato {formato}, máximo 150 palabras.",
        agent=agente,
    )


def tarea_editar(agente: Agent, post: str, formato: str) -> Task:
    """Tarea para el Editor: revisar y puntuar el post."""
    return Task(
        description=(
            f"Revisa el siguiente post de LinkedIn (formato: {formato}):\n\n"
            f"---\n{post}\n---\n\n"
            "Evalúa según estos criterios:\n"
            "- Primera línea: ¿para el scroll?\n"
            "- ¿Suena a persona real o a IA?\n"
            "- ¿Tiene valor concreto para el lector?\n"
            "- ¿Longitud correcta (máximo 150 palabras)?\n"
            "- ¿El cierre invita a interactuar?\n\n"
            "Devuelve ÚNICAMENTE un JSON con esta estructura:\n"
            '{\n'
            '  "puntuacion": <número del 1 al 10>,\n'
            '  "post_mejorado": "<el post mejorado>",\n'
            '  "razon_cambio": "<qué has cambiado y por qué>",\n'
            '  "formato_usado": "<storytelling o tecnico>"\n'
            '}'
        ),
        expected_output="JSON con puntuacion, post_mejorado, razon_cambio y formato_usado.",
        agent=agente,
    )


# ══════════════════════════════════════════════════════════════
# INSTRUCCIONES
# ══════════════════════════════════════════════════════════════
# Este módulo define las tareas (Tasks) de CrewAI.
#
# Cada tarea se asocia a un agente y recibe los parámetros
# necesarios según el momento del flujo.
#
# Uso:
#   from tasks import tarea_investigar, tarea_redactar, tarea_editar
#   from agents import crear_investigador, crear_redactor, crear_editor
#
#   inv = crear_investigador()
#   task = tarea_investigar(inv, "Agentes de IA en 2026")
# ══════════════════════════════════════════════════════════════
