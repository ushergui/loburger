AGENTS.md — LOL BURGUER (Sistema de Gestão)


Este arquivo define as regras permanentes do projeto. Todo agente deve ler este arquivo antes de executar qualquer tarefa nesta workspace e nunca contradizer o que está aqui, mesmo que um prompt pontual não repita essas regras.



1. IDENTIDADE DO PROJETO


Sistema de gestão interna (não é cardápio público) para a hamburgueria LOL BURGUER, temática de League of Legends (lanches nomeados como campeões).
Público do sistema: dono/gestão, operador de caixa, cozinha. Não é voltado ao cliente final.


2. STACK — NÃO ALTERAR SEM APROVAÇÃO EXPLÍCITA


Backend: Python 3.12+ / Django 5.x
Banco de dados: SQLite (db.sqlite3) — não sugerir Postgres/MySQL a menos que eu peça
Frontend: Tailwind CSS + HTMX + Alpine.js (sem React/Vue/frameworks JS pesados)
Gráficos: Chart.js (ou lib leve equivalente)
Ambiente-alvo: Windows 10/11, sem WSL, sem Docker obrigatório — tudo deve rodar com venv + pip puro
Nunca introduzir dependência paga, chave de API externa obrigatória ou serviço em nuvem para o sistema funcionar localmente


3. IDENTIDADE VISUAL (Design System — sempre aplicar, em toda tela nova)


Tema: Hextech/League of Legends, aplicado com sobriedade de painel de gestão (bonito, mas 100% legível e funcional)
Paleta obrigatória:

Fundo: azul-marinho profundo (#0A1428, #0A1E2C)
Primária/destaque: dourado Hextech (#C89B3C, #F0E6D2)
Secundária: azul Hextech (#0AC8B9, #0397AB)
Estados: sucesso (verde esmeralda), alerta (âmbar), erro (vermelho carmesim)



Tipografia: fonte com peso/serifada para títulos (ex: Cinzel/Marcellus), fonte legível para dados/corpo (ex: Inter/Rubik)
Nunca usar: logos, splash arts ou qualquer asset oficial da Riot Games — só paleta e linguagem visual inspirada
Nunca gerar: UI genérica de Bootstrap/admin cru — toda tela nova deve seguir o design system acima
Todo componente novo deve ser responsivo (mobile, tablet, desktop) por padrão, sem exceção


4. REGRAS DE NEGÓCIO INVIOLÁVEIS


Valores monetários sempre em Decimal, nunca float
Toda venda lançada deve gerar baixa automática de estoque dos ingredientes/embalagens via ficha técnica do produto
Cada canal de venda (iFood, iRango, Salão/Próprio) tem taxa e preço próprios — nunca tratar os 3 canais com a mesma regra/preço por padrão
Custo de produção e margem de lucro devem ser recalculados a partir da ficha técnica real, nunca hardcoded
Existem 2 perfis de acesso: Gestão (acesso total) e Operador/Caixa (restrito a vendas e visualização de estoque) — toda nova tela deve respeitar essa permissão


5. PADRÕES DE CÓDIGO


Organização em apps Django por domínio: produtos, estoque, vendas, relatorios, accounts/core
Toda lógica de negócio relevante (cálculo de custo, baixa de estoque, cálculo de lucro por canal) deve ser comentada em português
Preferir HTMX para qualquer interação que hoje recarregaria a página inteira (listar, filtrar, adicionar item, atualizar estoque)
Preferir Alpine.js para estado local de UI (modais, abas, toggles) — não usar para lógica de negócio/dados
Evitar N+1 queries: usar select_related/prefetch_related sempre que houver relação entre models
Toda listagem deve ter paginação


6. COMPORTAMENTO ESPERADO DO AGENTE


Antes de gerar uma tela/feature nova, verificar se ela é compatível com as seções 2 a 5 acima
Se uma solicitação pontual conflitar com este arquivo (ex: pedir uma cor fora da paleta, ou um banco diferente), o agente deve avisar o conflito antes de executar, não decidir sozinho
Se algo não puder ser implementado por limitação técnica, deixar isso explícito como pendência — nunca omitir silenciosamente
Ao criar uma nova página, sempre reaproveitar os componentes/base template já existentes (não recriar layout do zero a cada tela)