"""
Boot Shoppe - cliente compartilhado da Instagram Graph API
=============================================================
Config e funcoes de publicacao usadas tanto pelo app do webhook
(boot_shoppe_instagram.py) quanto pelo cron de posts diarios
(daily_publish.py). Mantido em um lugar so pra nao duplicar logica.
"""

import os
import time
import json
import logging
from datetime import date
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]  # variavel de ambiente do host (Railway), nunca no codigo
IG_USER_ID   = os.environ.get("IG_USER_ID", "27095478893447950")  # @ganhosonlinems
BASE_URL     = "https://graph.instagram.com/v21.0"

VERIFY_TOKEN_DEFAULT = "bootshoppetoken"  # mesmo valor usado antes; sobrescrito por IG_VERIFY_TOKEN no ambiente

# ─────────────────────────────────────────────
# Fila de posts diarios (compartilhada entre daily_publish.py e o bot de DM)
# ─────────────────────────────────────────────

QUEUE_PATH  = Path(__file__).parent / "content_queue.json"
QUEUE_EPOCH = date(2026, 7, 13)  # dia 0 da rotacao; nao mude isso depois de ja estar rodando

# Dados dos produtos por nome, usados tanto no PRODUCTS legado (media_id fixo)
# quanto para resolver automaticamente o produto do post publicado hoje.
CATALOGO_PRODUTOS = {
    "Bolsa de Ombro Feminina": {
        "nome":       "Bolsa de Ombro Feminina",
        "imagem_url": "https://raw.githubusercontent.com/marcosfare88-hue/boot-shoppe/main/assets/bolsa_romantic_crown.jpg",
        "link":       "https://s.shopee.com.br/5LA07sh1rC?share_channel_code=1",
    },
    "Jaqueta Feminina Puffer Forrada": {
        "nome":       "Jaqueta Feminina Puffer Forrada",
        "imagem_url": "https://raw.githubusercontent.com/marcosfare88-hue/boot-shoppe/main/assets/jaqueta_puffer.jpg",
        "link":       "https://s.shopee.com.br/3ViP1lLSLN?share_channel_code=1",
    },
    "Jogo de Lencol 400 Fios": {
        "nome":       "Jogo de Lencol 400 Fios",
        "imagem_url": "https://raw.githubusercontent.com/marcosfare88-hue/boot-shoppe/main/assets/lencol_400_fios.png",
        "link":       "https://s.shopee.com.br/4LHZxQJscD",
    },
}


def carregar_fila() -> list:
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        fila = json.load(f)
    if not fila:
        raise ValueError("content_queue.json esta vazio")
    return fila


def post_do_dia(hoje: date = None) -> dict:
    hoje = hoje or date.today()
    fila = carregar_fila()
    indice = (hoje - QUEUE_EPOCH).days % len(fila)
    return fila[indice]


def produto_do_dia() -> dict:
    """
    Resolve qual produto deveria estar no post de hoje, usando a mesma
    formula deterministica do daily_publish.py. Usado pelo bot de DM
    quando recebe comentario num media_id que nao esta no PRODUCTS
    legado (media_id fixo) - assim nao e preciso cadastrar manualmente
    cada post automatico novo.
    """
    post = post_do_dia()
    return CATALOGO_PRODUTOS.get(post.get("produto"))


def enviar_mensagem(recipient: dict, message: dict) -> dict:
    url = f"{BASE_URL}/{IG_USER_ID}/messages"
    resp = requests.post(
        url,
        params={"access_token": ACCESS_TOKEN},
        json={"recipient": recipient, "message": message},
        headers={"Content-Type": "application/json"}
    )
    return resp.json()


def _aguardar_container_pronto(creation_id: str, tentativas: int = 15, intervalo: float = 2.0) -> bool:
    """
    O Instagram processa a imagem de forma assincrona depois de criar o
    container; publicar antes disso falha com 'Media ID is not available'
    (codigo 9007). Espera o status_code virar FINISHED (ou ERROR) antes
    de seguir pro media_publish.
    """
    for _ in range(tentativas):
        resp = requests.get(
            f"{BASE_URL}/{creation_id}",
            params={"access_token": ACCESS_TOKEN, "fields": "status_code"}
        )
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            log.error(f"Container {creation_id} entrou em ERROR durante o processamento.")
            return False
        time.sleep(intervalo)
    log.error(f"Container {creation_id} nao ficou pronto a tempo (ultimo status: {status!r}).")
    return False


def publicar_post(image_url: str, caption: str) -> dict:
    """
    Publica um post de imagem simples no Instagram.

    Parametros:
        image_url  - URL publica da imagem
        caption    - legenda do post

    Retorna o resultado da publicacao.
    """
    log.info("Criando container de midia...")
    resp = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        params={"access_token": ACCESS_TOKEN},
        json={"image_url": image_url, "caption": caption}
    )
    resultado = resp.json()
    creation_id = resultado.get("id")
    if not creation_id:
        log.error(f"Erro ao criar container: {resultado}")
        return resultado

    if not _aguardar_container_pronto(creation_id):
        return {"error": "Container nao ficou pronto para publicacao", "creation_id": creation_id}

    log.info(f"Publicando container {creation_id}...")
    resp2 = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={"access_token": ACCESS_TOKEN},
        json={"creation_id": creation_id}
    )
    return resp2.json()


def publicar_carrossel(image_urls: list, caption: str) -> dict:
    """
    Publica um carrossel (ate 10 imagens) no Instagram.

    Parametros:
        image_urls - lista de URLs publicas das imagens
        caption    - legenda do carrossel (vai na primeira imagem)

    Retorna o resultado da publicacao.
    """
    if not image_urls:
        return {"error": "Nenhuma imagem fornecida"}
    if len(image_urls) > 10:
        image_urls = image_urls[:10]
        log.warning("Carrossel limitado a 10 imagens.")

    child_ids = []
    for i, url in enumerate(image_urls):
        log.info(f"Criando container filho {i+1}/{len(image_urls)}...")
        resp = requests.post(
            f"{BASE_URL}/{IG_USER_ID}/media",
            params={"access_token": ACCESS_TOKEN},
            json={"image_url": url, "is_carousel_item": True}
        )
        child = resp.json()
        child_id = child.get("id")
        if not child_id:
            log.error(f"Erro no filho {i+1}: {child}")
            return child
        child_ids.append(child_id)
        time.sleep(1)  # evita rate limit

    log.info("Criando container do carrossel...")
    resp2 = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        params={"access_token": ACCESS_TOKEN},
        json={
            "media_type": "CAROUSEL",
            "children":   ",".join(child_ids),
            "caption":    caption
        }
    )
    carrossel = resp2.json()
    creation_id = carrossel.get("id")
    if not creation_id:
        log.error(f"Erro ao criar carrossel: {carrossel}")
        return carrossel

    if not _aguardar_container_pronto(creation_id):
        return {"error": "Container do carrossel nao ficou pronto para publicacao", "creation_id": creation_id}

    log.info(f"Publicando carrossel {creation_id}...")
    resp3 = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={"access_token": ACCESS_TOKEN},
        json={"creation_id": creation_id}
    )
    return resp3.json()
