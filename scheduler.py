"""
scheduler.py — Trigger automático para los lunes a las 9:00.

Usa APScheduler para ejecutar el flujo automático cada lunes.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Referencia al callback que main.py registra
_job_callback = None


def set_job_callback(callback) -> None:
    """Registra la función que se ejecuta cada lunes a las 9:00."""
    global _job_callback
    _job_callback = callback


async def _ejecutar_job() -> None:
    """Wrapper que ejecuta el callback registrado."""
    if _job_callback:
        await _job_callback()


def crear_scheduler() -> AsyncIOScheduler:
    """
    Crea un scheduler que dispara el flujo automático
    cada lunes a las 9:00.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _ejecutar_job,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="linkedin_lunes",
        name="Post de LinkedIn semanal",
        replace_existing=True,
    )
    return scheduler


# ══════════════════════════════════════════════════════════════
# INSTRUCCIONES
# ══════════════════════════════════════════════════════════════
# Scheduler para el trigger automático de los lunes.
#
# Usa APScheduler con AsyncIOScheduler para ser compatible
# con el event loop de python-telegram-bot.
#
# Uso desde main.py:
#   from scheduler import crear_scheduler, set_job_callback
#
#   set_job_callback(mi_funcion_async)
#   scheduler = crear_scheduler()
#   scheduler.start()
#
# El job se ejecuta cada lunes a las 9:00 hora local.
# Para cambiar la hora, modifica hour y minute en CronTrigger.
# ══════════════════════════════════════════════════════════════
