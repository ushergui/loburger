from playwright.sync_api import sync_playwright
import time
import os

BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.join("media", "tutorial")

# Helper function to inject in browser
ANNOTATE_JS = """
function addAnnotation(selector, text, stepNum, position='bottom') {
    const el = document.querySelector(selector);
    if (!el) {
        console.error('Element not found:', selector);
        return;
    }
    
    // Draw thick border
    el.style.outline = '4px solid #F0E6D2';
    el.style.outlineOffset = '4px';
    el.style.position = 'relative';
    
    // Create label
    const label = document.createElement('div');
    label.innerHTML = `<span style="background: #0A1428; color: #F0E6D2; padding: 4px 10px; border-radius: 50%; font-weight: bold; font-family: monospace; border: 2px solid #F0E6D2; margin-right: 8px;">${stepNum}</span> <span style="font-family: sans-serif; font-size: 14px; font-weight: bold;">${text}</span>`;
    label.style.position = 'absolute';
    label.style.background = '#0A1E2C';
    label.style.color = 'white';
    label.style.padding = '8px 12px';
    label.style.borderRadius = '8px';
    label.style.border = '2px solid #F0E6D2';
    label.style.boxShadow = '0 10px 25px rgba(0,0,0,0.8)';
    label.style.zIndex = '999999';
    label.style.whiteSpace = 'nowrap';
    label.style.display = 'flex';
    label.style.alignItems = 'center';
    
    document.body.appendChild(label);
    
    const rect = el.getBoundingClientRect();
    if (position === 'bottom') {
        label.style.top = (rect.bottom + window.scrollY + 15) + 'px';
        label.style.left = (rect.left + window.scrollX) + 'px';
    } else if (position === 'right') {
        label.style.top = (rect.top + window.scrollY) + 'px';
        label.style.left = (rect.right + window.scrollX + 15) + 'px';
    } else if (position === 'top') {
        label.style.top = (rect.top + window.scrollY - 50) + 'px';
        label.style.left = (rect.left + window.scrollX) + 'px';
    } else if (position === 'left') {
        label.style.top = (rect.top + window.scrollY) + 'px';
        label.style.left = (rect.left + window.scrollX - label.offsetWidth - 15) + 'px';
    } else {
        // center
        label.style.top = (rect.top + window.scrollY + (rect.height/2)) + 'px';
        label.style.left = (rect.left + window.scrollX + (rect.width/2)) + 'px';
    }
}
"""

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        
        print("Logging in...")
        page.goto(f"{BASE_URL}/login/")
        page.fill('input[name="username"]', 'playwright')
        page.fill('input[name="password"]', 'playwright123')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        
        def take_step_screenshot(url, name, annotations):
            print(f"Processing {name} at {url}...")
            page.goto(f"{BASE_URL}{url}")
            page.wait_for_load_state('networkidle')
            time.sleep(1) # Extra time for Alpine/HTMX
            
            page.add_script_tag(content=ANNOTATE_JS)
            
            for selector, text, step_num, pos in annotations:
                page.evaluate(f"const e = document.querySelector('{selector}'); if(e) e.scrollIntoView({{behavior: 'instant', block: 'center'}});")
                time.sleep(0.5)
                page.evaluate(f"addAnnotation('{selector}', '{text}', '{step_num}', '{pos}')")
                
            time.sleep(1)
            filepath = os.path.join(OUTPUT_DIR, f"{name}.png")
            page.screenshot(path=filepath, full_page=True)
            print(f"Saved {filepath}")

        take_step_screenshot('/vendas/fechamento-diario/', 'fechamento', [
            ('input[name="data"]', 'Data de Referência', 1, 'bottom'),
            ('.bg-hex_dark_card table', 'Quantidades e Entregas', 2, 'bottom'),
            ('button[type="submit"]', 'Gravar Fechamento', 3, 'top')
        ])
        
        take_step_screenshot('/estoque/resumo/', 'estoque', [
            ('.grid > div:first-child', 'Quantidade Atual', 1, 'right'),
            ('.bg-hex_warning', 'Alerta Baixo / Crítico', 2, 'bottom')
        ])

        take_step_screenshot('/estoque/ajustar/', 'estoque_ajuste', [
            ('select[name="ingrediente"]', 'Selecionar Insumo', 1, 'bottom'),
            ('select[name="tipo"]', 'Entrada ou Ajuste', 2, 'right'),
            ('input[name="quantidade"]', 'Quantidade Comprada', 3, 'bottom')
        ])
        
        take_step_screenshot('/relatorios/dashboard/', 'dashboard', [
            ('select[name="mes"]', 'Navegar no Tempo', 1, 'bottom'),
            ('h2.text-2xl', 'Lucro Líquido Real', 2, 'bottom'),
            ('a.bg-hex_gold', 'Exportar Planilha CSV', 3, 'bottom')
        ])
        
        take_step_screenshot('/relatorios/despesas/', 'despesas', [
            ('a[href="/relatorios/despesa/novo/"]', 'Lançar Despesa', 1, 'bottom'),
            ('table tbody tr:first-child', 'Listagem (Fixo / Variável)', 2, 'bottom')
        ])
        
        take_step_screenshot('/produtos/', 'produtos', [
            ('a[href="/produtos/novo/"]', 'Cadastrar Lanche', 1, 'bottom'),
            ('table tbody tr:first-child td:nth-child(4)', 'Acesso à Ficha Técnica', 2, 'bottom')
        ])

        take_step_screenshot('/vendas/canais/', 'canais', [
            ('table tbody tr:first-child', 'Editar Taxas do Canal', 1, 'bottom')
        ])
        
        take_step_screenshot('/relatorios/despesas/', 'crud', [
            ('table tbody tr:first-child a.text-hex_blue', 'Botão Editar', '✏️', 'bottom'),
            ('table tbody tr:first-child a.text-hex_danger', 'Botão Excluir', '🗑️', 'bottom')
        ])
        
        browser.close()
        print("Done!")

if __name__ == "__main__":
    run()
