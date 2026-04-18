"""
get_linkedin_token.py — Obtener el access token de LinkedIn (una sola vez).

Ejecutar con: python get_linkedin_token.py

Requiere en .env:
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET

Al finalizar imprime las dos líneas para añadir a .env:
  LINKEDIN_ACCESS_TOKEN=...
  LINKEDIN_USER_ID=...
"""

import asyncio
import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import httpx
from dotenv import load_dotenv

load_dotenv()

REDIRECT_URI = "http://localhost:8000/callback"
SCOPE = "w_member_social r_liteprofile"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
ME_URL = "https://api.linkedin.com/v2/me?projection=(id)"

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autenticaci\xc3\xb3n completada. Puedes cerrar esta ventana.</h2>"
            )
        else:
            error = params.get("error", ["desconocido"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>Error: {error}</h2>".encode())

    def log_message(self, format, *args):
        pass  # silenciar logs del servidor HTTP


def _iniciar_servidor() -> HTTPServer:
    server = HTTPServer(("localhost", 8000), _CallbackHandler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server


async def main():
    client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print(
            "ERROR: Faltan LINKEDIN_CLIENT_ID o LINKEDIN_CLIENT_SECRET en .env\n"
            "Consulta .env.example para saber cómo obtenerlos."
        )
        sys.exit(1)

    # Construir URL de autorización
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("Iniciando servidor en http://localhost:8000/callback ...")
    _iniciar_servidor()

    print(f"\nAbriendo navegador para autorizar LinkedIn...")
    print(f"Si no se abre automáticamente, visita:\n  {url}\n")
    webbrowser.open(url)

    # Esperar hasta recibir el código (máx. 120 segundos)
    for _ in range(120):
        if _auth_code:
            break
        await asyncio.sleep(1)
    else:
        print("ERROR: No se recibió respuesta en 120 segundos.")
        sys.exit(1)

    print("Código recibido. Obteniendo access token...")

    async with httpx.AsyncClient() as client:
        # Intercambiar código por token
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": _auth_code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]

        # Obtener el ID del perfil
        resp_me = await client.get(
            ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp_me.raise_for_status()
        user_id = resp_me.json()["id"]

    print("\n" + "=" * 60)
    print("✅ Copia estas líneas en tu archivo .env:")
    print("=" * 60)
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
    print(f"LINKEDIN_USER_ID={user_id}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
