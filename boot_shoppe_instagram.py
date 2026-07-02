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

Antes de rodar, defina a variavel de ambiente IG_ACCESS_TOKEN com o seu
token do Instagram Graph API. NUNCA cole o token direto no codigo:
  - Local: crie um arquivo .env (nao commitado) ou exporte no terminal
  - Railway/Render: configure em Settings > Environment Variables

Para receber webhooks do Instagram voce precisa de uma URL publica.
Opcoes gratuitas: Railway (railway.app), Render (render.com), Replit (replit.com)
Para testar localmente: ngrok (ngrok.com) -> ngrok http 5000
"""

import os
import time
import logging
import unicodedata
import requests
from flask import Flask, request, jsonify


def _normalize(text: str) -> str:
    """minusculas e sem acentos, pra bater 'preco' com 'preço' etc."""
    text = text.lower()
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )

# ─────────────────────────────────────────────
# CONFIGURACOES - edite aqui
# ─────────────────────────────────────────────

ACCESS_TOKEN   = os.environ["IG_ACCESS_TOKEN"]   # defina isso nas variaveis de ambiente do host (Railway/Render), nunca no codigo
IG_USER_ID     = os.environ.get("IG_USER_ID", "27095478893447950")   # seu ID de usuario do Instagram (@ganhosonlinems)
VERIFY_TOKEN   = os.environ.get("IG_VERIFY_TOKEN", "bootshoppetoken")     # mesmo token cadastrado no Meta Developer

# Produtos por post (media_id do post -> dados do produto).
# O media_id de cada post aparece nos logs assim que alguem comenta nele
# (procure por "media_id=" no log). Adicione uma entrada nova aqui pra
# cada post/produto diferente que voce for divulgar.
PRODUCTS = {
    "18183735790400606": {
        "nome":       "Bolsa de Ombro Feminina",
        "imagem_url": "https://raw.githubusercontent.com/marcosfare88-hue/boot-shoppe/main/assets/bolsa_romantic_crown.jpg",
        "link":       "https://s.shopee.com.br/5LA07sh1rC?share_channel_code=1",
    },
    # "media_id_do_post": {
    #     "nome":       "Nome do produto",
    #     "imagem_url": "https://link-publico-da-foto.jpg",  # opcional
    #     "link":       "https://s.shopee.com.br/xxxxx",
    # },
}

# Usado quando o post comentado nao esta cadastrado em PRODUCTS acima
DEFAULT_PRODUCT = {
    "nome":       "produto",
    "imagem_url": None,
    "link":       "https://s.shopee.com.br/qhA641KYD",
}

# Palavras/frases que disparam o auto-reply (case-insensitive).
# Basta o comentario conter QUALQUER uma delas.
TRIGGER_WORDS = [
    "eu quero",
    "quero comprar",
    "quero um",
    "quero uma",
    "onde compro",
    "onde eu compro",
    "onde compra",
    "onde eu compra",
    "como compro",
    "como eu compro",
    "como compra",
    "quanto custa",
    "qual o preco",
    "qual e o preco",
    "qual o valor",
    "qual e o valor",
    "manda o link",
    "manda link",
    "me manda o link",
    "qual o link",
    "tem link",
    "link por favor",
    "onde encontro",
    "onde eu encontro",
    "onde acho",
    "onde eu acho",
]

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
            media_id     = value.get("media", {}).get("id", "")

            log.info(f"Comentario recebido: '{comment_text}' (id={comment_id}, media_id={media_id})")

            # Dispara auto-reply se contem qualquer uma das palavras-chave
            texto_normalizado = _normalize(comment_text)
            if comment_id and any(_normalize(kw) in texto_normalizado for kw in TRIGGER_WORDS):
                log.info(f"Palavra-chave detectada. Enviando DM para comentario {comment_id}...")
                resultado = enviar_dm_comentario(comment_id, media_id)
                log.info(f"DM enviada: {resultado}")

    return "ok", 200


# ─────────────────────────────────────────────
# FUNCOES DE INSTAGRAM
# ─────────────────────────────────────────────

def _enviar_mensagem(recipient: dict, message: dict) -> dict:
    url = f"{BASE_URL}/{IG_USER_ID}/messages"
    resp = requests.post(
        url,
        params={"access_token": ACCESS_TOKEN},
        json={"recipient": recipient, "message": message},
        headers={"Content-Type": "application/json"}
    )
    return resp.json()


def enviar_dm_comentario(comment_id: str, media_id: str = "") -> dict:
    """
    Envia mensagens privadas em resposta a um comentario, com o produto
    certo pro post que foi comentado.

    IMPORTANTE: pra quem nunca trocou mensagem com a conta antes, o
    Instagram so garante a entrega de UMA mensagem via resposta a
    comentario (comment_id) - as seguintes podem falhar com "outside of
    allowed window" (isso so funciona sem erro se ja existir uma
    conversa previa com aquela pessoa). Por isso o BOTAO com o link vai
    primeiro (e' o que precisa chegar sempre); texto explicativo e foto
    do produto sao um bonus best-effort mandado depois.
    """
    produto = PRODUCTS.get(media_id, DEFAULT_PRODUCT)

    # 1. Botao com o link - PRIMEIRO e via comment_id, pra garantir a entrega.
    resultado_botao = _enviar_mensagem({"comment_id": comment_id}, {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "button",
                "text": (
                    f"Oi! Que otimo que voce se interessou "
                    f"{'no ' + produto['nome'] if produto['nome'] != 'produto' else 'nele'}! 😍\n\n"
                    f"Toca no botao pra ver na Shopee (compra segura ✅):"
                ),
                "buttons": [{
                    "type": "web_url",
                    "url": produto["link"],
                    "title": "Ver produto na Shopee"
                }]
            }
        }
    })

    recipient_id = resultado_botao.get("recipient_id")
    if not recipient_id:
        log.error(f"Botao (mensagem principal) falhou, sem recipient_id: {resultado_botao}")
        return {"botao": resultado_botao, "texto": None, "foto": None}

    # 2. Texto e foto - bonus best-effort. Podem falhar em conversas novas
    # (janela de entrega), mas o link essencial ja foi garantido acima.
    resultado_texto = _enviar_mensagem({"id": recipient_id}, {
        "text": (
            "Qualquer duvida e so chamar aqui no Direct! 💛"
        )
    })

    resultado_foto = None
    if produto.get("imagem_url"):
        resultado_foto = _enviar_mensagem({"id": recipient_id}, {
            "attachment": {
                "type": "image",
                "payload": {"url": produto["imagem_url"], "is_reusable": True}
            }
        })

    return {"texto": resultado_texto, "foto": resultado_foto, "botao": resultado_botao}


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
