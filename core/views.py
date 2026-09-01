from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from core.decorators import gestao_required
from .models import LogAuditoria

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

def logout_usuario(request):
    logout(request)
    return redirect('login')

@login_required
def home_redirect(request):
    if request.user.role == 'GESTAO':
        return redirect('dashboard')
    else:
        return redirect('fechamento_diario')

@login_required
def tutorial_view(request):
    return render(request, 'core/tutorial.html')


@login_required
@gestao_required
def auditoria_listar(request):
    logs = LogAuditoria.objects.select_related('usuario').all()

    acao = request.GET.get('acao', '')
    modelo = request.GET.get('modelo', '')
    usuario = request.GET.get('usuario', '')
    if acao:
        logs = logs.filter(acao=acao)
    if modelo:
        logs = logs.filter(modelo=modelo)
    if usuario:
        logs = logs.filter(usuario_nome__icontains=usuario)

    paginator = Paginator(logs, 40)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    modelos = LogAuditoria.objects.order_by('modelo').values_list('modelo', flat=True).distinct()

    return render(request, 'core/auditoria.html', {
        'page_obj': page_obj,
        'acoes': LogAuditoria.ACOES,
        'modelos': modelos,
        'acao_sel': acao,
        'modelo_sel': modelo,
        'usuario_sel': usuario,
    })

