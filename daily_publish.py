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
  funciona mesmo se o processo cair e for reiniciado no mesmo dia. O bot
  de DM (boot_shoppe_instagram.py) usa a mesma formula (via ig_api.py)
  pra descobrir o produto certo quando alguem comenta num post que nao
  esta cadastrado no PRODUCTS legado.

Uso:
  python daily_publish.py             # publica o post do dia de verdade
  python daily_publish.py --dry-run   # so mostra qual post seria publicado
"""

import sys
import json
import logging

from ig_api import publicar_post, publicar_carrossel, carregar_fila, post_do_dia

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


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

    carregar_fila()  # valida que o arquivo existe e nao esta vazio
    post = post_do_dia()

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
