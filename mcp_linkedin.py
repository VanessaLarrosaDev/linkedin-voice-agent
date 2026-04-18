"""
mcp_linkedin.py — Integración con LinkedIn REST API v2.

Publica posts de texto o con imagen en LinkedIn.
Todas las credenciales se leen de variables de entorno.
"""

import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


def _headers() -> dict:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN no está configurado en .env")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _author_urn() -> str:
    user_id = os.getenv("LINKEDIN_USER_ID", "")
    if not user_id:
        raise ValueError("LINKEDIN_USER_ID no está configurado en .env")
    return f"urn:li:person:{user_id}"


async def _registrar_imagen(client: httpx.AsyncClient, imagen_bytes: bytes) -> str:
    """
    Registra una imagen en LinkedIn y la sube.
    Devuelve el asset URN para usar en el post.
    """
    author = _author_urn()

    # Paso 1: registrar el upload
    registro = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }

    resp = await client.post(
        f"{LINKEDIN_API_BASE}/assets?action=registerUpload",
        headers=_headers(),
        json=registro,
    )
    resp.raise_for_status()
    data = resp.json()

    upload_url = (
        data["value"]["uploadMechanism"]
        ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
        ["uploadUrl"]
    )
    asset_urn = data["value"]["asset"]

    # Paso 2: subir el binario de la imagen
    upload_headers = {
        "Authorization": _headers()["Authorization"],
        "Content-Type": "application/octet-stream",
    }
    resp_upload = await client.put(
        upload_url,
        headers=upload_headers,
        content=imagen_bytes,
    )
    resp_upload.raise_for_status()

    logger.info(f"Imagen subida a LinkedIn: {asset_urn}")
    return asset_urn


async def publicar(post: str, imagen_bytes: bytes | None = None) -> None:
    """
    Publica un post en LinkedIn.

    Args:
        post: Texto del post (máximo ~3000 caracteres en LinkedIn).
        imagen_bytes: Binario de la imagen (opcional). Si se proporciona,
                      se publica junto al texto.
    """
    author = _author_urn()

    async with httpx.AsyncClient(timeout=30.0) as client:
        if imagen_bytes:
            asset_urn = await _registrar_imagen(client, imagen_bytes)
            payload = {
                "author": author,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": post},
                        "shareMediaCategory": "IMAGE",
                        "media": [
                            {
                                "status": "READY",
                                "media": asset_urn,
                            }
                        ],
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }
        else:
            payload = {
                "author": author,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": post},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }

        resp = await client.post(
            f"{LINKEDIN_API_BASE}/ugcPosts",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()

    logger.info("Post publicado correctamente en LinkedIn")
