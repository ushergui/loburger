from django.contrib import admin
from .models import CanalVenda, Pedido, PedidoItem

class PedidoItemInline(admin.TabularInline):
    model = PedidoItem
    extra = 0
    readonly_fields = ['produto', 'quantidade', 'preco_unitario']

class PedidoAdmin(admin.ModelAdmin):
    list_display = ['id', 'data_criacao', 'cliente_nome', 'canal', 'valor_bruto', 'lucro_liquido', 'status']
    list_filter = ['status', 'canal', 'data_criacao']
    search_fields = ['id', 'cliente_nome']
    inlines = [PedidoItemInline]
    
    # Trava os valores financeiros e auditoria para evitar fraudes via painel admin
    readonly_fields = ['valor_bruto', 'taxas_canal', 'custo_ingredientes', 'lucro_liquido', 'estoque_baixado', 'data_criacao']

class CanalVendaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'taxa_comissao', 'taxa_fixa', 'dias_repasse']
    search_fields = ['nome']

admin.site.register(Pedido, PedidoAdmin)
admin.site.register(CanalVenda, CanalVendaAdmin)

