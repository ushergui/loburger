"""Auditoria: registra em LogAuditoria quem criou, alterou ou excluiu os
registros importantes do sistema."""
from decimal import Decimal

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .middleware import get_usuario_atual

# app_label.ModelName -> rótulo amigável e campos que interessam no diff
MODELOS_AUDITADOS = {
    'relatorios.Despesa': ('Despesa', ['descricao', 'credor', 'valor', 'status', 'categoria', 'data_vencimento', 'data_pagamento', 'forma_pagamento']),
    'relatorios.DespesaRecorrente': ('Despesa recorrente', ['descricao', 'credor', 'valor_base', 'frequencia', 'primeiro_vencimento', 'categoria', 'ativa']),
    'vendas.Pedido': ('Pedido / Venda', ['cliente_nome', 'canal_id', 'modo_pagamento', 'status', 'valor_bruto', 'lucro_liquido']),
    'estoque.MovimentacaoEstoque': ('Movimentação de estoque', ['ingrediente_id', 'tipo', 'quantidade', 'valor_unitario']),
    'produtos.Produto': ('Produto', ['nome', 'categoria', 'status', 'custo_aquisicao']),
    'produtos.Ingrediente': ('Ingrediente', ['nome', 'custo_unitario', 'estoque_atual', 'unidade_compra', 'unidade_medida']),
    'produtos.PrecoCanal': ('Preço por canal', ['produto_id', 'canal_id', 'preco']),
    'produtos.FichaTecnicaItem': ('Item de ficha técnica', ['produto_id', 'ingrediente_id', 'produto_componente_id', 'quantidade']),
    'vendas.CanalVenda': ('Canal de venda', ['nome', 'taxa_comissao', 'taxa_online', 'taxa_fixa']),
    'vendas.ConfiguracaoFinanceira': ('Configuração financeira', ['taxa_maquininha', 'taxa_entrega', 'caixa_inicial']),
    'vendas.Entregador': ('Entregador', ['nome', 'eh_socio', 'ativo']),
    'core.Usuario': ('Usuário', ['username', 'first_name', 'last_name', 'email', 'role', 'is_active', 'is_staff', 'is_superuser']),
}


def _chave(instance):
    meta = instance._meta
    return f"{meta.app_label}.{meta.object_name}"


def _serial(v):
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return v


@receiver(pre_save)
def _capturar_estado_anterior(sender, instance, **kwargs):
    if _chave(instance) not in MODELOS_AUDITADOS or not instance.pk:
        return
    try:
        instance._estado_anterior = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._estado_anterior = None


@receiver(post_save)
def _log_save(sender, instance, created, **kwargs):
    chave = _chave(instance)
    if chave not in MODELOS_AUDITADOS:
        return
    from .models import LogAuditoria

    rotulo, campos = MODELOS_AUDITADOS[chave]
    usuario = get_usuario_atual()
    usuario = usuario if getattr(usuario, 'is_authenticated', False) else None

    if created:
        LogAuditoria.objects.create(
            usuario=usuario, usuario_nome=(usuario.username if usuario else 'sistema'),
            acao='CRIOU', modelo=rotulo, objeto_id=str(instance.pk),
            descricao=str(instance)[:255], detalhes={},
        )
        return

    anterior = getattr(instance, '_estado_anterior', None)
    if anterior is None:
        return
    diff = {}
    for campo in campos:
        antes, agora = getattr(anterior, campo, None), getattr(instance, campo, None)
        if antes != agora:
            diff[campo] = {'de': _serial(antes), 'para': _serial(agora)}
    if not diff:
        return
    LogAuditoria.objects.create(
        usuario=usuario, usuario_nome=(usuario.username if usuario else 'sistema'),
        acao='ALTEROU', modelo=rotulo, objeto_id=str(instance.pk),
        descricao=str(instance)[:255], detalhes=diff,
    )


@receiver(post_delete)
def _log_delete(sender, instance, **kwargs):
    chave = _chave(instance)
    if chave not in MODELOS_AUDITADOS:
        return
    from .models import LogAuditoria

    rotulo = MODELOS_AUDITADOS[chave][0]
    usuario = get_usuario_atual()
    usuario = usuario if getattr(usuario, 'is_authenticated', False) else None
    LogAuditoria.objects.create(
        usuario=usuario, usuario_nome=(usuario.username if usuario else 'sistema'),
        acao='EXCLUIU', modelo=rotulo, objeto_id=str(instance.pk),
        descricao=str(instance)[:255], detalhes={},
    )
