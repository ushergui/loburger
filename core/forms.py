from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from produtos.forms import ThemeFormMixin

Usuario = get_user_model()

_ROLE_HELP = "Gestão vê tudo (financeiro, cadastros, relatórios). Operador só opera o dia a dia."


class SenhaMixin:
    """Adiciona e valida os campos de senha."""

    def _add_campos_senha(self, obrigatorio=True):
        self.fields['senha1'] = forms.CharField(
            label="Senha", widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
            required=obrigatorio,
        )
        self.fields['senha2'] = forms.CharField(
            label="Repetir a senha", widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
            required=obrigatorio,
        )

    def clean(self):
        cleaned = super().clean()
        s1, s2 = cleaned.get('senha1'), cleaned.get('senha2')
        if s1 or s2:
            if s1 != s2:
                self.add_error('senha2', "As duas senhas não são iguais.")
            else:
                try:
                    validate_password(s1, self.instance)
                except forms.ValidationError as e:
                    self.add_error('senha1', e)
        return cleaned


class UsuarioCriarForm(SenhaMixin, ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ['username', 'first_name', 'last_name', 'email', 'role']
        labels = {'username': "Nome de usuário (login)", 'first_name': "Nome", 'last_name': "Sobrenome"}
        widgets = {'username': forms.TextInput(attrs={'autocomplete': 'off'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_campos_senha(obrigatorio=True)
        self.fields['role'].help_text = _ROLE_HELP

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data['senha1'])
        if commit:
            usuario.save()
        return usuario


class UsuarioEditarForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'is_active']
        labels = {
            'username': "Nome de usuário (login)", 'first_name': "Nome",
            'last_name': "Sobrenome", 'is_active': "Acesso liberado",
        }

    def __init__(self, *args, **kwargs):
        self.usuario_logado = kwargs.pop('usuario_logado', None)
        super().__init__(*args, **kwargs)
        self.fields['role'].help_text = _ROLE_HELP

    def clean(self):
        cleaned = super().clean()
        editando_a_si = self.usuario_logado and self.instance.pk == self.usuario_logado.pk
        if editando_a_si:
            if not cleaned.get('is_active'):
                self.add_error('is_active', "Você não pode desativar o seu próprio acesso.")
            if cleaned.get('role') != 'GESTAO':
                self.add_error('role', "Você não pode rebaixar o seu próprio perfil.")
        # Não deixar ficar sem nenhum gestor ativo
        if cleaned.get('role') != 'GESTAO' or not cleaned.get('is_active'):
            outros_gestores = Usuario.objects.filter(role='GESTAO', is_active=True).exclude(pk=self.instance.pk)
            if not outros_gestores.exists():
                self.add_error(None, "Precisa existir pelo menos um usuário de Gestão ativo no sistema.")
        return cleaned


class ResetarSenhaForm(SenhaMixin, ThemeFormMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self._add_campos_senha(obrigatorio=True)
