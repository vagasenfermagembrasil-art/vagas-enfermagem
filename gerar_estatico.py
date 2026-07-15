import sqlite3
import os
from datetime import datetime

# Configurações do Banco e Arquivo de Saída
DB_FILE = 'vagas_enfermagem.db'
HTML_FILE = 'index.html'

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portal de Vagas de Enfermagem 🩺</title>
    <style>
        :root {
            --bg-color: #f0f4f8;
            --card-bg: #ffffff;
            --text-main: #1a202c;
            --text-muted: #4a5568;
            --primary: #0077b6;
            --primary-hover: #0096c7;
            --accent-urgent: #e63946;
            --border-color: #e2e8f0;
        }

        body {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .container {
            width: 100%;
            max-width: 600px;
            margin-top: 20px;
        }

        /* Área do Logotipo no Topo */
        .logo-container {
            display: flex;
            justify-content: center;
            margin-bottom: 15px;
        }

        .profile-logo {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            background-color: #e2e8f0;
            border: 3px solid var(--primary);
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
        }

        .profile-logo img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .placeholder-text {
            font-size: 0.8rem;
            color: var(--text-muted);
            font-weight: bold;
            text-align: center;
            padding: 5px;
        }

        header {
            text-align: center;
            margin-bottom: 25px;
        }

        header h1 {
            font-size: 1.8rem;
            color: var(--primary);
            margin: 5px 0;
            font-weight: 800;
        }

        header p {
            font-size: 0.95rem;
            color: var(--text-muted);
            margin: 0;
        }

        .update-badge {
            display: inline-block;
            background-color: #e2e8f0;
            color: var(--text-main);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-top: 10px;
        }

        /* Campo de Busca */
        .search-container {
            margin-bottom: 24px;
        }

        .search-input {
            width: 100%;
            padding: 14px 18px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            font-size: 1rem;
            box-sizing: border-box;
            outline: none;
            transition: all 0.2s ease;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        }

        .search-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(0, 119, 182, 0.15);
        }

        .vagas-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        /* Cards de Vagas */
        .card {
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
            display: block;
            transition: transform 0.2s ease;
        }

        .card:hover {
            transform: translateY(-2px);
        }

        .urgent-tag {
            position: absolute;
            top: 0;
            right: 0;
            background-color: var(--accent-urgent);
            color: white;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 4px 12px;
            border-bottom-left-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .card h2 {
            font-size: 1.25rem;
            margin: 0 0 8px 0;
            padding-right: 80px;
            color: var(--text-main);
        }

        .institution {
            font-size: 1rem;
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 12px;
        }

        .meta-info {
            font-size: 0.88rem;
            color: var(--text-muted);
            margin-bottom: 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }

        .location-badge {
            background-color: #edf2f7;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 600;
            color: var(--text-muted);
        }

        .deadline {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        /* Botões */
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }

        .btn {
            flex: 1;
            min-width: 120px;
            text-align: center;
            padding: 11px 14px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.9rem;
            text-decoration: none;
            transition: background-color 0.2s ease;
            box-sizing: border-box;
            display: inline-block;
        }

        .btn-primary {
            background-color: var(--primary);
            color: white;
        }

        .btn-primary:hover {
            background-color: var(--primary-hover);
        }

        .btn-secondary {
            background-color: #f7fafc;
            color: var(--text-muted);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background-color: #edf2f7;
            color: var(--text-main);
        }

        /* Rodapé e Botão TikTok */
        footer {
            margin-top: 40px;
            margin-bottom: 20px;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 15px;
        }

        .btn-tiktok {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background-color: #010101;
            color: white;
            padding: 12px 24px;
            border-radius: 30px;
            font-weight: 700;
            font-size: 0.95rem;
            text-decoration: none;
            box-shadow: 0 4px 10px rgba(0,0,0,0.15);
            transition: transform 0.2s ease, background-color 0.2s ease;
        }

        .btn-tiktok:hover {
            transform: scale(1.05);
            background-color: #111111;
        }

        .footer-copyright {
            font-size: 0.78rem;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Logotipo Centralizado -->
        <div class="logo-container">
            <div class="profile-logo">
                <img src="logo-vagas-enfermagem.jpeg" alt="Logo Vagas Enfermagem">
            </div>
        </div>

        <header>
            <h1>Oportunidades de Enfermagem 🩺</h1>
            <p>Vagas e qualificações oficiais atualizadas para o Brasil inteiro.</p>
            <div class="update-badge">Atualizado em: {DATA_ATUALIZACAO}</div>
        </header>

        <!-- Campo de Busca -->
        <div class="search-container">
            <input type="text" id="searchInput" class="search-input" placeholder="Buscar por cargo, instituição, cidade ou estado...">
        </div>

        <main class="vagas-list" id="vagasList">
            {LISTA_DE_VAGAS}
        </main>

        <footer>
            <!-- Botão de Redirecionamento do TikTok -->
            <a href="https://www.tiktok.com/@SEU_PERFIL_AQUI" target="_blank" rel="noopener" class="btn-tiktok">
                🎵 Siga no TikTok para vagas diárias
            </a>
            <div class="footer-copyright">
                Portal de Vagas de Enfermagem © {ANO_ATUAL}
            </div>
        </footer>
    </div>

    <!-- Script de Busca Instantânea -->
    <script>
        const searchInput = document.getElementById('searchInput');
        const cards = document.querySelectorAll('.card');

        searchInput.addEventListener('input', function() {
            const query = searchInput.value.toLowerCase().trim();

            cards.forEach(card => {
                const cargo = card.getAttribute('data-cargo').toLowerCase();
                const instituicao = card.getAttribute('data-instituicao').toLowerCase();
                const cidade = card.getAttribute('data-cidade').toLowerCase();
                const estado = card.getAttribute('data-estado').toLowerCase();

                if (cargo.includes(query) || instituicao.includes(query) || cidade.includes(query) || estado.includes(query)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    </script>
</body>
</html>
'''

CARD_TEMPLATE = '''
            <div class="card" data-cargo="{CARGO}" data-instituicao="{INSTITUICAO}" data-cidade="{CIDADE}" data-estado="{ESTADO}">
                {TAG_URGENTE}
                <h2>{CARGO}</h2>
                <div class="institution">{INSTITUICAO}</div>
                <div class="meta-info">
                    <span class="location-badge">📍 {CIDADE} - {ESTADO}</span>
                    <span class="deadline">📅 <strong>Prazo:</strong> {PRAZO}</span>
                </div>
                <div class="actions">
                    {BOTOES}
                </div>
            </div>
'''

def format_date_br(date_str):
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return date_str

def generate_html_from_db():
    if not os.path.exists(DB_FILE):
        print(f"ℹ️ Criando o banco de dados {DB_FILE}...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vagas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cargo TEXT NOT NULL,
                instituicao TEXT NOT NULL,
                cidade TEXT NOT NULL,
                estado TEXT NOT NULL,
                prazo DATE NOT NULL,
                link_inscricao TEXT,
                link_edital TEXT,
                urgente INTEGER DEFAULT 0,
                atuacao TEXT,
                email TEXT
            );
        ''')
        conn.commit()
        conn.close()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Garante a existência da tabela com o campo 'email'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cargo TEXT NOT NULL,
            instituicao TEXT NOT NULL,
            cidade TEXT NOT NULL,
            estado TEXT NOT NULL,
            prazo DATE NOT NULL,
            link_inscricao TEXT,
            link_edital TEXT,
            urgente INTEGER DEFAULT 0,
            atuacao TEXT,
            email TEXT
        );
    ''')
    conn.commit()

    # Executa verificação para garantir que a coluna 'email' existe mesmo se a tabela já existia antes
    try:
        cursor.execute("SELECT email FROM vagas LIMIT 1")
    except sqlite3.OperationalError:
        print("⚠️ Coluna 'email' não detectada na tabela existente. Adicionando coluna...")
        cursor.execute("ALTER TABLE vagas ADD COLUMN email TEXT")
        conn.commit()

    cursor.execute('''
        SELECT cargo, instituicao, cidade, estado, prazo, link_inscricao, link_edital, urgente, email
        FROM vagas
        ORDER BY data_cadastro DESC
    ''')

    rows = cursor.fetchall()
    conn.close()

    vagas_html = []

    for row in rows:
        cargo, instituicao, cidade, estado, prazo, link_insc, link_edital, urgente, email = row
        prazo_formatado = format_date_br(prazo)

        tag_urgente = '<div class="urgent-tag">Urgente</div>' if urgente == 1 else ''

        botoes = []
        if link_insc:
            botoes.append(f'<a href="{link_insc}" target="_blank" rel="noopener" class="btn btn-primary">Inscrever-se</a>')
        if link_edital:
            botoes.append(f'<a href="{link_edital}" target="_blank" rel="noopener" class="btn btn-secondary">Ver Edital</a>')
        if email:
            botoes.append(f'<a href="mailto:{email}?subject=Candidatura para vaga de {cargo}" rel="noopener" class="btn btn-secondary">Enviar E-mail</a>')

        if not botoes:
            botoes.append('<span class="btn btn-secondary" style="cursor: default;">Contato no Vídeo</span>')

        botoes_str = "\n".join(botoes)

        card = CARD_TEMPLATE.format(
            TAG_URGENTE=tag_urgente,
            CARGO=cargo,
            INSTITUICAO=instituicao,
            CIDADE=cidade,
            ESTADO=estado.upper() if estado else "",
            PRAZO=prazo_formatado,
            BOTOES=botoes_str
        )
        vagas_html.append(card)

    # Se ainda não houver vagas cadastradas no banco, mostra um aviso amigável na página
    vagas_html_str = "\n".join(vagas_html) if vagas_html else '<p style="text-align:center; color: var(--text-muted); padding: 40px;">Nenhuma vaga cadastrada no momento. Volte em breve!</p>'
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")

    final_html = HTML_TEMPLATE.replace("{DATA_ATUALIZACAO}", now_str)
    final_html = final_html.replace("{LISTA_DE_VAGAS}", vagas_html_str)
    final_html = final_html.replace("{ANO_ATUAL}", str(datetime.now().year))

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print("✅ Site HTML local gerado com sucesso!")

if __name__ == '__main__':
    generate_html_from_db()
