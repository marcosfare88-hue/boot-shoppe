"""
Boot Shoppe - publicador diario
==================================
Pensado pra rodar como um Cron Job do Railway (servico separado do
webhook), sem depender de nada alem do repo + variaveis de ambiente
(IG_ACCESS_TOKEN). Roda, publica o post do dia, sai.

Como escolhe o post do dia:
  Le content_queue.json (lista de posts prontos) e calcula
      indice = (dias desde EPOCH) % tamanho_da_fila
  Isso e deterministico: nao precisa gravar estado em lugar nenhum, e
  funciona mesmo se o processo cair e for reiniciado no mesmo dia.

Uso:
  python daily_publish.py             # publica o post do dia de verdade
  python daily_publish.py --dry-run   # so mostra qual post seria publicado
"""

import sys
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from ig_api import publicar_post, publicar_carrossel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

QUEUE_PATH = Path(__file__).parent / "content_queue.json"
EPOCH = date(2026, 7, 13)  # dia 0 da rotacao; nao precisa mudar isso depois


def carregar_fila() -> list:
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        fila = json.load(f)
    if not fila:
        raise ValueError("content_queue.json esta vazio")
    return fila


def post_do_dia(fila: list, hoje: date = None) -> dict:
    hoje = hoje or date.today()
    dias_passados = (hoje - EPOCH).days
    indice = dias_passados % len(fila)
    return fila[indice]


def publicar(post: dict) -> dict:
    caption = post["caption"]
    if post["type"] == "carousel":
        return publicar_carrossel(post["image_urls"], caption)
    elif post["type"] == "image":
        return publicar_post(post["image_url"], caption)
    else:
        raise ValueError(f"Tipo de post desconhecido: {post['type']!r}")


def main():
    dry_run = "--dry-run" in sys.argv

    fila = carregar_fila()
    post = post_do_dia(fila)

    log.info(f"Post do dia: produto={post.get('produto')!r} tipo={post['type']!r}")

    if dry_run:
        log.info(f"[DRY RUN] Nao vou publicar de verdade. Conteudo: {json.dumps(post, ensure_ascii=False, indent=2)}")
        return

    resultado = publicar(post)
    log.info(f"Resultado da publicacao: {resultado}")

    if "id" not in resultado:
        log.error("Publicacao parece ter falhado (sem 'id' na resposta).")
        sys.exit(1)


if __name__ == "__main__":
    main()
