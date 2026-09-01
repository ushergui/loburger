from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout, get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from core.decorators import gestao_required
from .models import LogAuditoria
from .forms import UsuarioCriarForm, UsuarioEditarForm, ResetarSenhaForm

Usuario = get_user_model()

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


# ==========================================
# USUÁRIOS E PERFIS (GESTÃO)
# ==========================================

@login_required
@gestao_required
def usuario_listar(request):
    usuarios = Usuario.objects.all().order_by('-is_active', 'username')
    return render(request, 'core/usuarios_lista.html', {'usuarios': usuarios})


@login_required
@gestao_required
def usuario_criar(request):
    if request.method == 'POST':
        form = UsuarioCriarForm(request.POST)
        if form.is_valid():
            u = form.save()
            messages.success(request, f"Usuário '{u.username}' criado como {u.get_role_display()}.")
            return redirect('usuario_listar')
    else:
        form = UsuarioCriarForm()
    return render(request, 'core/usuario_form.html', {'form': form, 'titulo': "Novo Usuário", 'modo': 'criar'})


@login_required
@gestao_required
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario, usuario_logado=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Usuário '{usuario.username}' atualizado.")
            return redirect('usuario_listar')
    else:
        form = UsuarioEditarForm(instance=usuario, usuario_logado=request.user)
    return render(request, 'core/usuario_form.html', {
        'form': form, 'titulo': f"Editar: {usuario.username}", 'modo': 'editar', 'alvo': usuario,
    })


@login_required
@gestao_required
def usuario_resetar_senha(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        form = ResetarSenhaForm(request.POST, instance=usuario)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['senha1'])
            usuario.save()
            messages.success(request, f"Senha de '{usuario.username}' redefinida. Passe a nova senha para a pessoa.")
            return redirect('usuario_listar')
    else:
        form = ResetarSenhaForm(instance=usuario)
    return render(request, 'core/usuario_resetar_senha.html', {'form': form, 'alvo': usuario})


@login_required
@gestao_required
def usuario_excluir(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "Você não pode excluir a sua própria conta.")
        return redirect('usuario_listar')
    if usuario.role == 'GESTAO' and usuario.is_active:
        outros = Usuario.objects.filter(role='GESTAO', is_active=True).exclude(pk=usuario.pk)
        if not outros.exists():
            messages.error(request, "Não dá para excluir o único usuário de Gestão ativo.")
            return redirect('usuario_listar')
    if request.method == 'POST':
        nome = usuario.username
        usuario.delete()
        messages.success(request, f"Usuário '{nome}' excluído.")
        return redirect('usuario_listar')
    return render(request, 'core/usuario_confirm_delete.html', {'alvo': usuario})

