from django.contrib import admin
from .models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal

class FichaTecnicaItemInline(admin.TabularInline):
    model = FichaTecnicaItem
    fk_name = 'produto'
    extra = 1

class PrecoCanalInline(admin.TabularInline):
    model = PrecoCanal
    extra = 1

class ProdutoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'categoria', 'custo_total', 'status']
    list_filter = ['categoria', 'status']
    search_fields = ['nome', 'descricao']
    inlines = [FichaTecnicaItemInline, PrecoCanalInline]

class IngredienteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'categoria', 'estoque_atual', 'estoque_minimo', 'custo_unitario', 'status_estoque']
    list_filter = ['categoria']
    search_fields = ['nome', 'fornecedor']

admin.site.register(Produto, ProdutoAdmin)
admin.site.register(Ingrediente, IngredienteAdmin)

