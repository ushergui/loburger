from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('fluxo-caixa/', views.fluxo_caixa_projetado, name='fluxo_caixa_projetado'),
    path('exportar-csv/', views.exportar_csv, name='exportar_csv'),
    path('despesas/', views.despesa_listar, name='despesa_listar'),
    path('despesas/novo/', views.despesa_criar, name='despesa_criar'),
    path('despesas/<int:id>/editar/', views.despesa_editar, name='despesa_editar'),
    path('despesas/<int:id>/pagar/', views.despesa_marcar_paga, name='despesa_marcar_paga'),
    path('despesas/<int:id>/excluir/', views.despesa_excluir, name='despesa_excluir'),
    
    path('despesas/recorrente/novo/', views.despesa_recorrente_criar, name='despesa_recorrente_criar'),
    path('despesas/recorrente/<int:id>/editar/', views.despesa_recorrente_editar, name='despesa_recorrente_editar'),
    path('despesas/recorrente/<int:id>/excluir/', views.despesa_recorrente_excluir, name='despesa_recorrente_excluir'),
    
    path('notificacoes-badge/', views.notificacoes_badge, name='notificacoes_badge'),
]
