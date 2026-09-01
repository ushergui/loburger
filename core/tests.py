from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from core.models import LogAuditoria

Usuario = get_user_model()


class GestaoUsuariosTests(TestCase):
    def setUp(self):
        self.gestor = Usuario.objects.create_user('gestor', password='SenhaForte123', role='GESTAO')
        self.operador = Usuario.objects.create_user('caixa', password='SenhaForte123', role='OPERADOR')
        self.c = Client()

    def test_operador_nao_acessa(self):
        self.c.force_login(self.operador)
        r = self.c.get('/usuarios/')
        self.assertEqual(r.status_code, 302)  # redireciona para home

    def test_criar_usuario_com_perfil(self):
        self.c.force_login(self.gestor)
        r = self.c.post('/usuarios/novo/', {
            'username': 'esposa', 'first_name': 'Maria', 'last_name': '', 'email': '',
            'role': 'GESTAO', 'senha1': 'OutraSenha456', 'senha2': 'OutraSenha456',
        })
        self.assertEqual(r.status_code, 302)
        u = Usuario.objects.get(username='esposa')
        self.assertEqual(u.role, 'GESTAO')
        self.assertTrue(u.check_password('OutraSenha456'))
        self.assertTrue(LogAuditoria.objects.filter(modelo='Usuário', acao='CRIOU', objeto_id=str(u.id)).exists())

    def test_senha_diferente_falha(self):
        self.c.force_login(self.gestor)
        r = self.c.post('/usuarios/novo/', {
            'username': 'x', 'role': 'OPERADOR', 'senha1': 'AbcAbc123', 'senha2': 'zzz',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username='x').exists())

    def test_resetar_senha(self):
        self.c.force_login(self.gestor)
        r = self.c.post(f'/usuarios/{self.operador.id}/senha/', {
            'senha1': 'NovaSenha789', 'senha2': 'NovaSenha789',
        })
        self.assertEqual(r.status_code, 302)
        self.operador.refresh_from_db()
        self.assertTrue(self.operador.check_password('NovaSenha789'))

    def test_nao_pode_ficar_sem_gestor(self):
        self.c.force_login(self.gestor)
        # tentar rebaixar o único gestor
        r = self.c.post(f'/usuarios/{self.gestor.id}/editar/', {
            'username': 'gestor', 'first_name': '', 'last_name': '', 'email': '',
            'role': 'OPERADOR', 'is_active': 'on',
        })
        self.assertEqual(r.status_code, 200)
        self.gestor.refresh_from_db()
        self.assertEqual(self.gestor.role, 'GESTAO')

    def test_nao_pode_excluir_a_si_mesmo(self):
        self.c.force_login(self.gestor)
        r = self.c.post(f'/usuarios/{self.gestor.id}/excluir/')
        self.assertTrue(Usuario.objects.filter(id=self.gestor.id).exists())

    def test_bloquear_acesso_mantem_cadastro(self):
        outro = Usuario.objects.create_user('g2', password='SenhaForte123', role='GESTAO')
        self.c.force_login(self.gestor)
        r = self.c.post(f'/usuarios/{outro.id}/editar/', {
            'username': 'g2', 'first_name': '', 'last_name': '', 'email': '',
            'role': 'GESTAO', 'is_active': '',
        })
        self.assertEqual(r.status_code, 302)
        outro.refresh_from_db()
        self.assertFalse(outro.is_active)
