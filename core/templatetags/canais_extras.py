"""Helpers de template para os canais de venda (logos do iFood / UaiRango)."""
from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Combina um pedaço do nome do canal com o arquivo de logo em static/img/.
_LOGOS = (
    ('ifood', 'img/ifood.png', 'iFood'),
    ('uai', 'img/uairango.png', 'UaiRango'),
)


def _logo_para(nome):
    alvo = (nome or '').lower()
    for chave, caminho, rotulo in _LOGOS:
        if chave in alvo:
            return static(caminho), rotulo
    return None, None


@register.simple_tag
def canal_logo(nome, tamanho=18):
    """<img> pequeno com a logo do canal, ou string vazia se não houver logo."""
    url, rotulo = _logo_para(nome)
    if not url:
        return ''
    return format_html(
        '<img src="{}" alt="{}" width="{}" height="{}" '
        'class="inline-block rounded object-contain shrink-0 align-middle" '
        'style="width:{}px;height:{}px;">',
        url, rotulo, tamanho, tamanho, tamanho, tamanho,
    )


@register.filter
def canal_logo_url(nome):
    """Só a URL da logo (ou '')."""
    url, _ = _logo_para(nome)
    return url or ''
