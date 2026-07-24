from django.contrib import admin
from .models import MovimentacaoEstoque

class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ['data_movimentacao', 'ingrediente', 'quantidade', 'tipo', 'responsavel']
    list_filter = ['tipo', 'data_movimentacao']
    search_fields = ['ingrediente__nome', 'observacao']
    readonly_fields = ['data_movimentacao'] # Não permite adulterar datas de auditoria

admin.site.register(MovimentacaoEstoque, MovimentacaoEstoqueAdmin)

