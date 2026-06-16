"""
Boot Shoppe - Instagram Automation
====================================
Substitui o Make.com para:
1. Responder comentarios automaticamente com link da Shopee
2. Publicar posts (imagem simples) no Instagram
3. Publicar carrosseis no Instagram

Como rodar:
  pip install flask requests
  python boot_shoppe_instagram.py

Para receber webhooks do Instagram voce precisa de uma URL publica.
Opcoes gratuitas: Railway (railway.app), Render (render.com), Replit (replit.com)
Para testar localmente: ngrok (ngrok.com) -> ngrok http 5000
"""

import os
import time
import logging
import requests
from flask import Flask, request, jsonify

# ─────────────────────────────────────────────
# CONFIGURACOES - edite aqui
# ─────────────────────────────────────────────

ACCESS_TOKEN   = "IGAAX8ym7NpzJBZAFpfZAmpqZAjFDclJBWDBnZA2U5SlZA2Y1psOHV6TzdrSmxRb2JtdlBkanZAIeVpBOEszRjVMQ0xMWWc4SjZAqVVFQWE9WN3ZAsVGpmWmxFeDFVRlc1LVVJYVRiX2NSbWFVMzZAULWpfY1dpTE1zRnFoRE1qaERpdDJmawZDZD"
IG_USER_ID     = "17841470360881988"   # seu ID de usuario do Instagram
VERIFY_TOKEN   = "bootshoppetoken"     # mesmo token cadastrado no Meta Developer

# Mensagem enviada automaticamente no DM ao detectar "eu quero" no comentario
AUTO_REPLY_MSG = (
    "Oi! Que otimo que voce se interessou! 😍\n\n"
    "Aqui esta o link do produto pra voce garantir o seu agora: 👇\n\n"
    "https://s.shopee.com.br/qhA641KYD\n\n"
    "Compra segura pela Shopee! 🛍️✅\n"
    "Qualquer duvida e so chamar aqui no Direct! 💛"
)

# Palavra-chave que dispara o auto-reply (case-insensitive)
TRIGGER_WORD   = "eu quero"

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
BASE_URL = f"https://graph.instagram.com/v21.0"


# ─────────────────────────────────────────────
# WEBHOOK - verificacao e recepcao de eventos
# ─────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    """Meta chama esse endpoint GET para verificar o webhook."""
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        log.info("Webhook verificado com sucesso.")
        return challenge, 200
    else:
        log.warning("Falha na verificacao do webhook.")
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    """Recebe eventos do Instagram (comentarios, mencoes, etc.)."""
    data = request.get_json(silent=True)
    if not data:
        return "No data", 400

    # So processa eventos do Instagram
    if data.get("object") != "instagram":
        return "ok", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            comment_text = value.get("text", "")
            comment_id   = value.get("id", "")

            log.info(f"Comentario recebido: '{comment_text}' (id={comment_id})")

            # Dispara auto-reply se contem a palavra-chave
            if TRIGGER_WORD in comment_text.lower() and comment_id:
                log.info(f"Palavra-chave detectada. Enviando DM para comentario {comment_id}...")
                resultado = enviar_dm_comentario(comment_id)
                log.info(f"DM enviada: {resultado}")

    return "ok", 200


# ─────────────────────────────────────────────
# FUNCOES DE INSTAGRAM
# ─────────────────────────────────────────────

def enviar_dm_comentario(comment_id: str) -> dict:
    """
    Envia uma mensagem privada em resposta a um comentario.
    Requer permissao instagram_manage_messages no app Meta.
    """
    url = f"{BASE_URL}/{IG_USER_ID}/messages"
    payload = {
        "recipient": {"comment_id": comment_id},
        "message":   {"text": AUTO_REPLY_MSG}
    }
    resp = requests.post(
        url,
        params={"access_token": ACCESS_TOKEN},
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    return resp.json()


def publicar_post(image_url: str, caption: str) -> dict:
    """
    Publica um post de imagem simples no Instagram.

    Parametros:
        image_url  - URL publica da imagem (ex: link do Google Drive publico)
        caption    - legenda do post

    Retorna o resultado da publicacao.
    """
    # 1. Cria container de midia
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

    # 2. Publica
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

    # 1. Cria container filho para cada imagem
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

    # 2. Cria container do carrossel
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

    # 3. Publica
    log.info(f"Publicando carrossel {creation_id}...")
    time.sleep(2)  # aguarda processamento
    resp3 = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={"access_token": ACCESS_TOKEN},
        json={"creation_id": creation_id}
    )
    return resp3.json()


# ─────────────────────────────────────────────
# EXEMPLOS DE USO DIRETO (sem webhook)
# ─────────────────────────────────────────────

def exemplo_publicar_post():
    resultado = publicar_post(
        image_url="https://link-publico-da-sua-imagem.jpg",
        caption="Confira nosso produto! 🥾 https://s.shopee.com.br/qhA641KYD"
    )
    print("Post publicado:", resultado)


def exemplo_publicar_carrossel():
    resultado = publicar_carrossel(
        image_urls=[
            "https://link-imagem-1.jpg",
            "https://link-imagem-2.jpg",
            "https://link-imagem-3.jpg",
        ],
        caption="Veja nosso catalogo! 🥾 https://s.shopee.com.br/qhA641KYD"
    )
    print("Carrossel publicado:", resultado)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Para testar publicacao direta, descomente uma linha abaixo:
    # exemplo_publicar_post()
    # exemplo_publicar_carrossel()

    # Inicia o servidor webhook
    port = int(os.environ.get("PORT", 5000))
    log.info(f"Servidor rodando na porta {port}")
    log.info("Endpoint do webhook: /webhook")
    app.run(host="0.0.0.0", port=port)
