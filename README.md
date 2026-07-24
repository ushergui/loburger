# LOL BURGUER — Sistema de Gestão Interna Hextech

Este é o sistema completo de gestão interna (ERP/PDV) da hamburgueria temática **LOL BURGUER**. O painel atende às necessidades dos gestores, operadores de caixa e equipe de cozinha.

---

## ⚡ Recursos Principais

1. **Cadastro e Ficha Técnica:** Cadastro visual de insumos e produtos (campeões). Cálculo automático de custo de fabricação e margens líquidas estimadas de lucro.
2. **Controle de Estoque Inteligente:** Baixa automática física de ingredientes e embalagens conforme a ficha técnica ao faturar um pedido. Movimentações manuais de reposição e descarte.
3. **Ponto de Venda (Caixa):** Lançamento ultra veloz de pedidos integrando canais (Salão, iFood, iRango) com comissões específicas de canais. Lógicas de carrinho em sessão e reatividade com HTMX.
4. **Dashboard Gerencial:** Scorecards de KPIs gerenciais, histórico de faturamento e lucro com gráficos ricos (Chart.js) e exportação de relatórios gerenciais para Excel (CSV).
5. **Nível de Acesso (Segurança):** Divisão de funcionalidades entre perfis `Gestão` (acesso total) e `Operador` (vendas e estoque, sem dados financeiros consolidados).

---

## 🛠️ Stack Tecnológica

- **Backend:** Python 3.12+ / Django 5.x
- **Banco de Dados:** SQLite (arquivo local `db.sqlite3` plug-and-play)
- **Frontend:** Tailwind CSS (via CDN), HTMX (requisições assíncronas), Alpine.js (modais e estados)
- **Gráficos:** Chart.js

---

## 🚀 Como Executar no Windows (Passo a Passo)

### 1. Clonar e Acessar o Diretório
Abra o terminal (PowerShell ou CMD) na pasta raiz do projeto:
```powershell
cd c:\Users\Pichau\Desktop\lolburger
```

### 2. Configurar o Ambiente Virtual (`venv`)
Crie e ative o ambiente virtual para isolar as dependências do projeto:
```powershell
# Cria o ambiente virtual
python -m venv venv

# Ativa o ambiente virtual (no PowerShell)
.\venv\Scripts\Activate.ps1
```

### 3. Instalar Dependências
Instale o Django e o Pillow (suporte a imagens):
```powershell
pip install -r requirements.txt
```

### 4. Aplicar Migrações do Banco de Dados
Gere e execute as migrações para estruturar o banco de dados SQLite local:
```powershell
python manage.py makemigrations core produtos estoque vendas
python manage.py migrate
```

### 5. Popular o Banco (Semear Dados)
Execute o comando customizado para popular o banco de dados com canais, 15 ingredientes, 7 produtos temáticos com fichas técnicas, e um histórico retroativo de 30 dias com 108 vendas:
```powershell
python manage.py seed
```

### 6. Iniciar o Servidor de Desenvolvimento
Inicie o servidor local do Django:
```powershell
python manage.py runserver
```
O sistema estará disponível em: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🔑 Credenciais de Acesso (Seed)

Após rodar o comando `python manage.py seed`, os seguintes usuários estarão pré-cadastrados para testes rápidos:

1. **Yasuo (Perfil Gestor / Admin):**
   - **Usuário:** `gestor`
   - **Senha:** `lol123password`
   - *Acesso total ao Dashboard, Auditoria de Estoque, Cadastro de Produtos e Preços por Canal.*

2. **Teemo (Perfil Operador / Caixa):**
   - **Usuário:** `caixa`
   - **Senha:** `lol123password`
   - *Acesso restrito ao Ponto de Venda (Lançar Pedidos), Painel de Fila de Produção e Visualização de Estoque Atual.*

*(Opcional) Para criar um novo superusuário administrador do Django nativo:*
```powershell
python manage.py createsuperuser
```
O painel nativo do Django pode ser acessado em [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).
