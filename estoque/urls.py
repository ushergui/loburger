from django.urls import path
from . import views

urlpatterns = [
    path('resumo/', views.estoque_resumo, name='estoque_resumo'),
    path('historico/', views.estoque_historico, name='estoque_historico'),
    path('ajustar/', views.estoque_ajustar, name='estoque_ajustar'),
    path('compra/', views.estoque_compra, name='estoque_compra'),
    path('compra/editar/<int:despesa_id>/', views.estoque_compra_editar, name='estoque_compra_editar'),
    path('buscar-ingredientes/', views.estoque_buscar_ingredientes, name='estoque_buscar_ingredientes'),
]
