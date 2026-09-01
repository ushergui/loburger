from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required

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

