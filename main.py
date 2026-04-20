"""
main.py — Orquestador principal de linkedin-voice-agent.

Lógica de decisión en Python (no en agentes):
1. Detectar modo (automático lunes 9:00 / manual por Telegram)
2. Detectar formato (storytelling / técnico / preguntar)
3. Consultar memoria antes de generar
4. Bucle de mejora automática si puntuación < 7
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from crewai import Crew

from agents import crear_investigador, crear_redactor, crear_editor
from tasks import (
    tarea_investigar,
    tarea_proponer_temas,
    tarea_redactar,
    tarea_editar,
)
from memory import guardar_post, tema_repetido
from telegram_bot import (
    crear_app,
    enviar_mensaje,
    enviar_y_esperar_respuesta,
    get_pending_photo,
    set_message_callback,
)
from scheduler import crear_scheduler, set_job_callback

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Palabras clave para detección de formato ─────────────────

PALABRAS_STORYTELLING = {
    "ponencia", "proyecto", "cliente", "reunión", "hoy", "ayer",
    "experiencia", "aprendí", "descubrí", "me pasó", "nos pasó",
    "historia", "anécdota", "viví", "trabajé", "conseguí",
}

PALABRAS_TECNICO = {
    "herramienta", "modelo", "agente", "ia", "inteligencia artificial",
    "automatización", "claude", "api", "framework", "código",
    "python", "crewai", "langchain", "gpt", "llm", "prompt",
    "deploy", "integración", "pipeline", "datos", "mcp",
}

MAX_INTENTOS_EDITOR = 2


# ══════════════════════════════════════════════════════════════
# DETECCIÓN DE FORMATO
# ══════════════════════════════════════════════════════════════

def detectar_formato(tema: str) -> str | None:
    """
    Detecta el formato del post según palabras clave del tema.
    Devuelve "storytelling", "tecnico" o None si no está claro.
    """
    tema_lower = tema.lower()
    score_story = sum(1 for p in PALABRAS_STORYTELLING if p in tema_lower)
    score_tech = sum(1 for p in PALABRAS_TECNICO if p in tema_lower)

    if score_story > score_tech and score_story > 0:
        return "storytelling"
    if score_tech > score_story and score_tech > 0:
        return "tecnico"
    return None


# ══════════════════════════════════════════════════════════════
# FLUJO DE GENERACIÓN
# ══════════════════════════════════════════════════════════════

async def flujo_generacion(tema: str, formato: str) -> None:
    """
    Flujo completo de generación de un post:
    1. Comprobar memoria
    2. Investigar
    3. Redactar
    4. Editar (con reintentos)
    5. Enviar a Vanessa para aprobación
    6. Publicar o iterar
    """
    global _flujo_activo
    _flujo_activo = True
    logger.info(f"Iniciando flujo de generación — tema: '{tema}', formato: {formato}")

    # ── 1. Comprobar memoria ─────────────────────────────────
    repetido, temas_similares = tema_repetido(tema)
    if repetido:
        aviso = (
            f"He detectado que este tema es similar a posts recientes:\n"
            + "\n".join(f"  • {t}" for t in temas_similares)
            + "\n\nSugiero un ángulo distinto. ¿Quieres continuar igualmente? (sí/no)"
        )
        respuesta = await enviar_y_esperar_respuesta(aviso)
        if respuesta.lower() not in ("sí", "si", "s", "yes"):
            await enviar_mensaje("Entendido. Envíame otro tema cuando quieras.")
            return

    # ── 2. Investigar ────────────────────────────────────────
    await enviar_mensaje(f"Investigando sobre '{tema}'...")

    investigador = crear_investigador()
    task_inv = tarea_investigar(investigador, tema)
    crew_inv = Crew(agents=[investigador], tasks=[task_inv], verbose=True)
    resultado_inv = crew_inv.kickoff()
    contexto = str(resultado_inv)

    logger.info("Investigación completada")

    # ── 3 y 4. Redactar + Editar (con reintentos) ───────────
    redactor = crear_redactor()
    editor = crear_editor()
    feedback_editor = ""
    resultado_editor = None

    for intento in range(1, MAX_INTENTOS_EDITOR + 1):
        logger.info(f"Intento de redacción {intento}/{MAX_INTENTOS_EDITOR}")

        # Redactar
        task_red = tarea_redactar(
            redactor, tema, formato, contexto, feedback_editor
        )
        crew_red = Crew(agents=[redactor], tasks=[task_red], verbose=True)
        resultado_red = crew_red.kickoff()
        post_borrador = str(resultado_red)

        # Editar
        task_edit = tarea_editar(editor, post_borrador, formato)
        crew_edit = Crew(agents=[editor], tasks=[task_edit], verbose=True)
        resultado_edit = crew_edit.kickoff()

        # Parsear JSON del editor
        resultado_editor = _parsear_resultado_editor(str(resultado_edit))

        if resultado_editor is None:
            logger.warning("No se pudo parsear la respuesta del editor")
            resultado_editor = {
                "puntuacion": 5,
                "post_mejorado": post_borrador,
                "razon_cambio": "Error al parsear respuesta del editor",
                "formato_usado": formato,
            }

        puntuacion = resultado_editor["puntuacion"]
        logger.info(f"Puntuación del editor: {puntuacion}/10")

        if puntuacion >= 7:
            break

        # Si la puntuación es baja y quedan intentos, pasar feedback
        feedback_editor = resultado_editor["razon_cambio"]
        logger.info(f"Puntuación baja ({puntuacion}). Reintentando con feedback...")

    # ── 5. Enviar a Vanessa ──────────────────────────────────
    post_final = resultado_editor["post_mejorado"]
    puntuacion_final = resultado_editor["puntuacion"]

    nota_revision = ""
    if puntuacion_final < 7:
        nota_revision = "\n⚠️ Nota: este post no alcanzó la puntuación mínima. Requiere revisión."

    mensaje_aprobacion = (
        f"Tu post de esta semana:\n"
        f"──────────────────\n"
        f"{post_final}\n"
        f"──────────────────\n"
        f"Puntuación: {puntuacion_final}/10{nota_revision}\n\n"
        f"✅ Escribe PUBLICAR para aprobar\n"
        f"✏️ O escribe tus comentarios para mejorar"
    )

    # ── 6. Bucle de aprobación ───────────────────────────────
    while True:
        respuesta = await enviar_y_esperar_respuesta(mensaje_aprobacion)

        if not respuesta:
            await enviar_mensaje("No recibí respuesta. El post queda pendiente.")
            _flujo_activo = False
            return

        if respuesta.upper() == "PUBLICAR":
            # Descargar imagen adjunta si Vanessa envió una foto
            imagen_bytes: bytes | None = None
            foto_info = get_pending_photo()
            if foto_info:
                from telegram import Bot
                bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
                file = await bot.get_file(foto_info["file_id"])
                imagen_bytes = bytes(await file.download_as_bytearray())

            await _publicar_linkedin(post_final, imagen_bytes)

            # Guardar en memoria
            guardar_post({
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "tema": tema,
                "formato": formato,
                "puntuacion_editor": puntuacion_final,
                "publicado": True,
            })

            await enviar_mensaje("¡Post publicado en LinkedIn! 🎉")
            logger.info("Post publicado exitosamente")
            _flujo_activo = False
            return

        # Vanessa envió comentarios → rehacer con su feedback
        await enviar_mensaje("Rehaciendo el post con tus comentarios...")

        task_red = tarea_redactar(
            redactor, tema, formato, contexto,
            feedback_editor=f"Comentarios de Vanessa: {respuesta}"
        )
        crew_red = Crew(agents=[redactor], tasks=[task_red], verbose=True)
        resultado_red = crew_red.kickoff()
        post_borrador = str(resultado_red)

        task_edit = tarea_editar(editor, post_borrador, formato)
        crew_edit = Crew(agents=[editor], tasks=[task_edit], verbose=True)
        resultado_edit = crew_edit.kickoff()

        resultado_editor = _parsear_resultado_editor(str(resultado_edit))
        if resultado_editor is None:
            resultado_editor = {
                "puntuacion": 5,
                "post_mejorado": post_borrador,
                "razon_cambio": "Error al parsear",
                "formato_usado": formato,
            }

        post_final = resultado_editor["post_mejorado"]
        puntuacion_final = resultado_editor["puntuacion"]

        mensaje_aprobacion = (
            f"Post actualizado:\n"
            f"──────────────────\n"
            f"{post_final}\n"
            f"──────────────────\n"
            f"Puntuación: {puntuacion_final}/10\n\n"
            f"✅ Escribe PUBLICAR para aprobar\n"
            f"✏️ O escribe tus comentarios para mejorar"
        )


# ══════════════════════════════════════════════════════════════
# MODO AUTOMÁTICO (lunes 9:00)
# ══════════════════════════════════════════════════════════════

async def modo_automatico() -> None:
    """
    Flujo automático que se ejecuta cada lunes a las 9:00:
    1. Investigador propone 3 temas
    2. Vanessa elige uno
    3. Se detecta formato y se genera el post
    """
    logger.info("Ejecutando modo automático (lunes 9:00)")

    investigador = crear_investigador()
    task_temas = tarea_proponer_temas(investigador)
    crew_temas = Crew(agents=[investigador], tasks=[task_temas], verbose=True)
    resultado = crew_temas.kickoff()

    temas_texto = str(resultado).strip()

    mensaje = (
        f"¡Buenos días Vanessa! Temas de esta semana:\n\n"
        f"{temas_texto}\n\n"
        f"Responde con 1, 2 o 3"
    )

    respuesta = await enviar_y_esperar_respuesta(mensaje)

    # Parsear la elección
    temas_lista = _parsear_temas(temas_texto)

    if respuesta in ("1", "2", "3"):
        idx = int(respuesta) - 1
        if idx < len(temas_lista):
            tema = temas_lista[idx]
        else:
            tema = temas_lista[0]
    else:
        # Si no es un número, usar la respuesta como tema personalizado
        tema = respuesta

    formato = detectar_formato(tema)
    if formato is None:
        resp_formato = await enviar_y_esperar_respuesta(
            "¿Es una experiencia personal o un tema técnico?\n"
            "Responde: personal / técnico"
        )
        formato = (
            "storytelling" if "personal" in resp_formato.lower()
            else "tecnico"
        )

    await flujo_generacion(tema, formato)


# ══════════════════════════════════════════════════════════════
# MODO MANUAL (mensaje de Telegram)
# ══════════════════════════════════════════════════════════════

_flujo_activo = False


async def modo_manual(texto: str) -> None:
    """
    Flujo manual cuando Vanessa envía un tema por Telegram.
    Detecta que no es una respuesta numérica y arranca la generación.
    """
    global _flujo_activo

    # Ignorar si hay un flujo en curso (el mensaje es una respuesta interna)
    if _flujo_activo:
        return

    logger.info(f"Modo manual activado — mensaje: '{texto}'")

    # Ignorar si es una respuesta a otra interacción
    if texto.upper() in ("PUBLICAR", "SÍ", "SI", "NO", "1", "2", "3",
                         "PERSONAL", "TÉCNICO", "TECNICO"):
        return

    tema = texto
    formato = detectar_formato(tema)

    if formato is None:
        resp = await enviar_y_esperar_respuesta(
            "¿Es una experiencia personal o un tema técnico?\n"
            "Responde: personal / técnico"
        )
        formato = (
            "storytelling" if "personal" in resp.lower()
            else "tecnico"
        )

    await flujo_generacion(tema, formato)


# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════

def _parsear_resultado_editor(texto: str) -> dict | None:
    """Extrae el JSON de la respuesta del editor."""
    try:
        # Buscar JSON en la respuesta
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if match:
            data = json.loads(match.group())
            # Validar campos requeridos
            if all(k in data for k in ("puntuacion", "post_mejorado",
                                        "razon_cambio", "formato_usado")):
                data["puntuacion"] = int(data["puntuacion"])
                return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _parsear_temas(texto: str) -> list[str]:
    """Extrae los temas numerados de la respuesta del investigador."""
    temas = []
    for linea in texto.strip().split("\n"):
        linea = linea.strip()
        # Eliminar numeración (1. , 1) , 1- , etc.)
        limpia = re.sub(r"^[\d]+[.\-)\s]+", "", linea).strip()
        if limpia:
            temas.append(limpia)
    return temas[:3]


async def _publicar_linkedin(post: str, imagen_bytes: bytes | None = None) -> None:
    """Publica el post en LinkedIn, opcionalmente con imagen."""
    logger.info("Publicando en LinkedIn...")
    logger.info(f"Post: {post[:80]}...")
    from mcp_linkedin import publicar
    await publicar(post, imagen_bytes)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

async def main() -> None:
    """Arranca el bot de Telegram y el scheduler."""
    logger.info("Iniciando linkedin-voice-agent...")

    # Configurar el callback del scheduler (lunes 9:00)
    set_job_callback(modo_automatico)
    scheduler = crear_scheduler()
    scheduler.start()
    logger.info("Scheduler configurado: lunes a las 9:00")

    # Configurar el callback para mensajes manuales
    set_message_callback(lambda texto: asyncio.create_task(modo_manual(texto)))

    # Arrancar el bot de Telegram
    app = crear_app()
    logger.info("Bot de Telegram iniciado. Esperando mensajes...")

    # Inicializar y ejecutar con polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Mantener el proceso vivo
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Deteniendo...")
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


# ══════════════════════════════════════════════════════════════
# INSTRUCCIONES DE INSTALACIÓN Y EJECUCIÓN
# ══════════════════════════════════════════════════════════════
#
# 1. INSTALACIÓN:
#    pip install -r requirements.txt
#
# 2. CONFIGURAR .env:
#    Copia .env y rellena las variables:
#
#    ANTHROPIC_API_KEY:
#      → https://console.anthropic.com/settings/keys
#      → Crea una nueva API key y pégala
#
#    TELEGRAM_BOT_TOKEN:
#      → Abre Telegram y busca @BotFather
#      → Envía /newbot, sigue instrucciones
#      → Copia el token que te da
#
#    TELEGRAM_CHAT_ID:
#      → Envía un mensaje a tu bot
#      → Visita https://api.telegram.org/bot<TOKEN>/getUpdates
#      → Busca "chat":{"id": XXXXXXX}
#
#    LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET:
#      → https://www.linkedin.com/developers/apps
#      → Crea una app, ve a "Auth" y copia los datos
#      → Añade http://localhost:8000/linkedin/callback como Redirect URI
#
# 3. EJECUTAR:
#    python main.py
#
#    El bot arrancará y:
#    - Escuchará mensajes de Telegram (modo manual)
#    - Cada lunes a las 9:00 propondrá temas (modo automático)
#
# 4. PROBAR:
#    Envía un mensaje a tu bot con un tema, por ejemplo:
#    "Agentes de IA con CrewAI para automatizar procesos"
#
# ══════════════════════════════════════════════════════════════
