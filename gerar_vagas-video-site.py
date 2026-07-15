"""
==============================================
  GERADOR DE VÍDEOS - VAGAS ENFERMAGEM
  Versão sincronizada com locução automática PT-BR
==============================================

O que esta versão faz:
1) Gera o vídeo MP4 com os dados da vaga aparecendo no card.
2) Quebra textos longos, links e e-mails no card, sem cortar no lado direito.
3) Gera texto curto de locução (.txt), sem repetir cidade/estado de forma confusa.
4) Gera legenda pronta para TikTok (_legenda_tiktok.txt).
5) Gera voz automática em português do Brasil usando edge-tts.
6) Calcula a duração real da locução e distribui a entrada dos textos ao longo do vídeo.
7) Separa os itens do card com espaçamento visual maior entre cada campo.
8) Mostra o card completo no início, dá uma “piscada” limpa e depois reconstrói os dados lentamente.
9) Junta áudio e vídeo em MP4 compatível com TikTok: H.264 + AAC.

Instalação necessária uma única vez:
    python3 -m pip install edge-tts opencv-python pillow numpy
    sudo apt install ffmpeg

Como usar:
1) Deixe este script na mesma pasta de:
   - card_base.png
   - vagas.csv
2) Execute:
   python3 gerar_vagas-video-site.py
3) Os arquivos finais ficam em:
   videos_gerados/

FORMATO DO CSV ATUALIZADO:
estado,cidade,cargo1,cargo2,instituicao,atuacao,link_site,email
"""

import asyncio
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── CONFIGURAÇÕES GERAIS ──────────────────────────────────────
CARD_BASE   = "card_base.png"
OUTPUT_DIR  = "videos_gerados"
CSV_FILE    = "vagas.csv"

# Ajuste os caminhos se suas fontes estiverem em outra pasta.
FONT_BOLD   = "/home/silviocdc/.fonts/Poppins-Bold.ttf"
FONT_REG    = "/home/silviocdc/.fonts/Poppins-Regular.ttf"

FPS              = 30
DURACAO_MIN_SEG  = 12       # duração mínima; aumenta automaticamente se a locução for maior
MARGEM_AUDIO_SEG = 0.8      # pequena sobra no final do vídeo após a locução
WHITE            = (255, 255, 255, 255)

# ── CONFIGURAÇÕES DA VOZ ──────────────────────────────────────
GERAR_LOCUCAO_AUTOMATICA = True

# Voz masculina PT-BR do Microsoft Edge TTS.
TTS_VOICE  = "pt-BR-AntonioNeural"
TTS_RATE   = "+10%"    
TTS_VOLUME = "+0%"     

# Se True, mantém também o vídeo sem áudio. Para uso normal, deixe False.
MANTER_VIDEO_SEM_AUDIO = False

# Área segura do texto dentro do card
TEXT_X      = 55
TEXT_RIGHT  = 565
FIELD_SIZE  = 19
LINE_H      = 27

# Espaço extra depois de cada item do card.
FIELD_GAP_AFTER = 16

# Ordem visual dos campos ajustada para incluir Site e E-mail separadamente
ORDEM_CAMPOS = [
    'estado',
    'cidade',
    'cargo1',
    'cargo2',
    'instituicao',
    'atuacao',
    'link_site',
    'email'
]

# Ajustes da sincronização visual.
INICIO_TIMELINE_SEG       = 1.0
MARGEM_FINAL_TIMELINE_SEG = 3.0
FADE_DUR                  = 0.75

# ── ABERTURA / GANCHO VISUAL ──────────────────────────────────
MOSTRAR_CARD_COMPLETO_INICIO = True
CARD_COMPLETO_INICIO_SEG     = 2.00   
PISCADA_CARD_LIMPO_SEG       = 0.45   
PAUSA_APOS_PISCADA_SEG       = 0.15   


# ── UTILITÁRIOS DE TEXTO ──────────────────────────────────────

def load_font(path, size, bold=False):
    """Carrega a fonte desejada; se não encontrar, usa uma fonte padrão do sistema."""
    candidates = [path]

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ])

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)

    return ImageFont.load_default()


def text_width(draw, text, font):
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return bbox[2] - bbox[0]


def split_long_token(draw, token, font, max_width):
    """Quebra palavras/URLs/E-mails muito longas, que não têm espaço."""
    parts = []
    cur = ""

    for ch in str(token):
        test = cur + ch
        if cur and text_width(draw, test, font) > max_width:
            parts.append(cur)
            cur = ch
        else:
            cur = test

    if cur:
        parts.append(cur)

    return parts


def wrap_value(draw, value, font, first_width, next_width):
    """Quebra texto considerando largura menor na primeira linha e maior nas demais."""
    tokens = str(value or "").split()
    lines = []
    cur = ""
    line_index = 0

    def current_width():
        return first_width if line_index == 0 else next_width

    for token in tokens:
        avail = current_width()
        test = token if not cur else f"{cur} {token}"

        if text_width(draw, test, font) <= avail:
            cur = test
            continue

        if cur:
            lines.append(cur)
            cur = ""
            line_index += 1
            avail = current_width()

        if text_width(draw, token, font) > avail:
            chunks = split_long_token(draw, token, font, avail)
            for chunk in chunks[:-1]:
                lines.append(chunk)
                line_index += 1
                avail = current_width()
            cur = chunks[-1]
        else:
            cur = token

    if cur:
        lines.append(cur)

    return lines


def contato_para_card(contato):
    """Remove https:// e www. para caber melhor no card visual."""
    contato = str(contato or "").strip()
    if not contato:
        return ""

    if contato.startswith(("http://", "https://")):
        parsed = urlparse(contato)
        compact = f"{parsed.netloc}{parsed.path}".strip("/")
        if parsed.query:
            compact += "?..."
        return compact.replace("www.", "")

    return contato.replace("www.", "")


def extrair_uf(estado):
    """Extrai a sigla da UF de textos como 'RIO DE JANEIRO (RJ)'."""
    estado = str(estado or "").strip()
    match = re.search(r"\(([A-Za-z]{2})\)", estado)
    if match:
        return match.group(1).upper()

    if len(estado) == 2 and estado.isalpha():
        return estado.upper()

    return "BR"


def limpar_nome_estado(estado):
    """Remove a sigla entre parênteses, mantendo só o nome do estado."""
    estado = str(estado or "").strip()
    estado = re.sub(r"\s*\([A-Za-z]{2}\)\s*$", "", estado).strip()
    return estado


def local_para_locucao(vaga):
    """Monta local curto e dinâmico para a voz."""
    cidade = str(vaga.get('cidade', '') or '').strip()
    estado = str(vaga.get('estado', '') or '').strip()
    uf = extrair_uf(estado)
    estado_nome = limpar_nome_estado(estado)

    if cidade and uf != "BR":
        return f"{cidade}, {uf}"
    if cidade and estado_nome:
        return f"{cidade}, {estado_nome}"
    if cidade:
        return cidade
    if estado_nome and uf != "BR":
        return f"{estado_nome}, {uf}"
    return estado_nome or estado or "Brasil"


def remover_acentos(texto):
    texto = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")


def hashtag_fragmento(texto):
    texto = remover_acentos(texto)
    partes = re.findall(r"[A-Za-z0-9]+", texto)
    return "".join(p.capitalize() for p in partes)


def nome_arquivo_seguro(texto):
    texto = remover_acentos(str(texto or ""))
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "vaga"


def cargos_texto(vaga):
    cargo1 = str(vaga.get('cargo1', '') or '').strip()
    cargo2 = str(vaga.get('cargo2', '') or '').strip()

    if cargo1 and cargo2:
        return f"{cargo1} e {cargo2}"
    return cargo1 or cargo2 or "profissionais de enfermagem"


def cargo_para_fala(cargo):
    """Deixa o cargo mais natural para locução."""
    cargo = str(cargo or "").strip()
    if not cargo:
        return ""

    cargo = re.sub(r"\s+", " ", cargo)

    if re.search(r"enfermeir", remover_acentos(cargo).lower()):
        if not re.search(r"tecnic", remover_acentos(cargo).lower()):
            return "enfermeiro ou enfermeira"

    if re.search(r"tecnic", remover_acentos(cargo).lower()):
        return "técnico ou técnica de enfermagem"

    cargo = cargo.replace("(o)", "").replace("(a)", "")
    return re.sub(r"\s+", " ", cargo).strip().lower()


def cargos_para_locucao(vaga):
    cargo1 = cargo_para_fala(vaga.get('cargo1', ''))
    cargo2 = cargo_para_fala(vaga.get('cargo2', ''))
    cargos = [c for c in [cargo1, cargo2] if c]

    unicos = []
    for cargo in cargos:
        if cargo not in unicos:
            unicos.append(cargo)

    if len(unicos) == 2:
        return f"{unicos[0]} e {unicos[1]}"
    if len(unicos) == 1:
        return unicos[0]
    return "profissionais de enfermagem"


def gerar_hashtags(vaga, limite=5):
    uf = extrair_uf(vaga.get('estado', ''))
    cidade = vaga.get('cidade', '')
    cargos = remover_acentos(cargos_texto(vaga).lower())

    tags = [
        f"#VagasEnfermagem{uf}",
        f"#VagasEnfermagem{hashtag_fragmento(cidade)}",
    ]

    if "enfermeir" in cargos:
        tags.extend(["#Enfermeiro", "#Enfermeira"])

    if "tecnic" in cargos:
        tags.append("#TecnicoDeEnfermagem")

    tags.extend(["#Enfermagem", "#VagasEnfermagem", "#EmpregoEnfermagem"])

    final = []
    for tag in tags:
        if tag and tag not in final:
            final.append(tag)

    return final[:limite]


def campo_tem_conteudo(vaga, campo):
    """Indica se um campo deve participar da animação visual."""
    valor = str(vaga.get(campo, "") or "").strip()
    if campo in ["estado", "cidade"]:
        return bool(valor)
    if campo == "link_site":
        return bool(contato_para_card(valor))
    if campo == "email":
        return bool(valor)
    return bool(valor)


def campos_visiveis_com_conteudo(vaga):
    return {campo for campo in ORDEM_CAMPOS if campo_tem_conteudo(vaga, campo)}


def inicio_animacao_pos_abertura():
    if not MOSTRAR_CARD_COMPLETO_INICIO:
        return INICIO_TIMELINE_SEG

    return max(
        INICIO_TIMELINE_SEG,
        CARD_COMPLETO_INICIO_SEG + PISCADA_CARD_LIMPO_SEG + PAUSA_APOS_PISCADA_SEG,
    )


def calcular_timeline_visual(vaga, duracao_seg):
    campos = [campo for campo in ORDEM_CAMPOS if campo_tem_conteudo(vaga, campo)]

    if not campos:
        return []

    inicio = inicio_animacao_pos_abertura()
    limite_inicio = max(0.2, duracao_seg - MARGEM_FINAL_TIMELINE_SEG - 1.0)
    inicio = min(inicio, limite_inicio)
    fim = max(inicio, duracao_seg - MARGEM_FINAL_TIMELINE_SEG)

    if len(campos) == 1:
        return [(campos[0], inicio)]

    passo = (fim - inicio) / (len(campos) - 1)
    return [(campo, inicio + idx * passo) for idx, campo in enumerate(campos)]


# ── RENDERIZAÇÃO DO CARD ──────────────────────────────────────

def wrap_field(draw, label, value, y, line_h=LINE_H):
    if not value:
        return y

    font_b = load_font(FONT_BOLD, FIELD_SIZE, bold=True)
    font_v = load_font(FONT_REG, FIELD_SIZE, bold=False)

    label_text = f"{label}: "
    label_w = text_width(draw, label_text, font_b)
    total_w = TEXT_RIGHT - TEXT_X
    first_w = max(80, total_w - label_w)

    lines = wrap_value(draw, value, font_v, first_w, total_w)

    for i, line in enumerate(lines):
        if i == 0:
            draw.text((TEXT_X, y), label_text, font=font_b, fill=WHITE)
            draw.text((TEXT_X + label_w, y), line, font=font_v, fill=WHITE)
        else:
            draw.text((TEXT_X, y), line, font=font_v, fill=WHITE)
        y += line_h

    return y + FIELD_GAP_AFTER


def render_frame(vaga, visible):
    img = Image.open(CARD_BASE).convert('RGBA')
    draw = ImageDraw.Draw(img)

    font_b24 = load_font(FONT_BOLD, 24, bold=True)
    font_r20 = load_font(FONT_REG, 20, bold=False)

    if 'estado' in visible:
        draw.text((300, 255), vaga.get('estado', ''), font=font_b24, fill=WHITE, anchor="mm")
    if 'cidade' in visible:
        draw.text((300, 285), f"Cidade: {vaga.get('cidade', '')}", font=font_r20, fill=WHITE, anchor="mm")

    if any(f in visible for f in ['cargo1', 'cargo2', 'instituicao', 'atuacao', 'link_site', 'email']):
        y = 325
        if 'cargo1' in visible:
            y = wrap_field(draw, "Cargo", vaga.get('cargo1', ''), y)
        if 'cargo2' in visible:
            y = wrap_field(draw, "Cargo", vaga.get('cargo2', ''), y)
        if 'instituicao' in visible:
            y = wrap_field(draw, "Instituição", vaga.get('instituicao', ''), y)
        if 'atuacao' in visible:
            y = wrap_field(draw, "Atuação", vaga.get('atuacao', ''), y)
        if 'link_site' in visible:
            y = wrap_field(draw, "Inscrição", contato_para_card(vaga.get('link_site', '')), y)
        if 'email' in visible:
            y = wrap_field(draw, "E-mail", vaga.get('email', ''), y)

    return img


def blend(img_a, img_b, alpha):
    a = np.array(img_a.convert('RGB')).astype(float)
    b = np.array(img_b.convert('RGB')).astype(float)
    return Image.fromarray((a * (1 - alpha) + b * alpha).astype(np.uint8))


def pil_to_cv2(img):
    arr = np.array(img.convert('RGB'))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


# ── TEXTOS ────────────────────────────────────────────────────

def gerar_texto_locucao(vaga, output_path):
    """Gera arquivo .txt com texto curto para locução."""
    cargos = cargos_para_locucao(vaga)
    local = local_para_locucao(vaga)
    instituicao = str(vaga.get('instituicao', '') or '').strip()
    atuacao = str(vaga.get('atuacao', '') or '').strip()
    link_site = str(vaga.get('link_site', '') or '').strip()
    email = str(vaga.get('email', '') or '').strip()

    partes = [
        f"Atenção enfermagem! Oportunidade para {cargos} em {local}.",
    ]

    if instituicao:
        partes.append(f"Instituição: {instituicao}.")

    if atuacao:
        partes.append(f"Atuação: {atuacao}.")

    if link_site or email:
        partes.append("Para se inscrever, confira as informações de contato na legenda do vídeo. Acesse o link em nossa Bio e busque outras vagas de seu interesse!")

    partes.append("Siga o canal Vagas Enfermagem e receba oportunidades todos os dias.")

    texto = " ".join(partes).strip()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(texto)

    return texto


def gerar_texto_legenda_tiktok(vaga, output_path):
    """Gera legenda pronta para colar no TikTok."""
    uf = extrair_uf(vaga.get('estado', ''))
    cidade = str(vaga.get('cidade', '') or '').strip()
    cargos = cargos_texto(vaga)
    instituicao = str(vaga.get('instituicao', '') or '').strip()
    atuacao = str(vaga.get('atuacao', '') or '').strip()
    link_site = str(vaga.get('link_site', '') or '').strip()
    email = str(vaga.get('email', '') or '').strip()
    hashtags = " ".join(gerar_hashtags(vaga))

    titulo = f"[{uf}] Vaga para {cargos} - {cidade}"

    linhas = [
        titulo,
        "",
        f"Cargos: {cargos}.",
    ]

    if instituicao:
        linhas.append(f"Instituição: {instituicao}.")

    if atuacao:
        linhas.append(f"Atuação: {atuacao}.")

    if link_site:
        linhas.append(f"Site para Inscrição: {link_site}")
        
    if email:
        linhas.append(f"E-mail para Envio: {email}")

    linhas.extend([
        "",
        "Siga o Vagas Enfermagem para receber oportunidades todos os dias. Acesse o link da Bio para realizar buscas em nosso website de vagas",
        "",
        hashtags,
    ])

    texto = "\n".join(linhas).strip()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(texto)

    return texto


# ── ÁUDIO E VÍDEO ─────────────────────────────────────────────

async def _edge_tts_save(texto, audio_path):
    import edge_tts
    communicate = edge_tts.Communicate(
        texto,
        voice=TTS_VOICE,
        rate=TTS_RATE,
        volume=TTS_VOLUME,
    )
    await communicate.save(audio_path)


def gerar_audio_locucao(texto, audio_path):
    if not GERAR_LOCUCAO_AUTOMATICA:
        return False

    try:
        asyncio.run(_edge_tts_save(texto, audio_path))
        return True
    except ModuleNotFoundError:
        print("   ❌ O pacote edge-tts não está instalado.")
        return False
    except Exception as exc:
        print(f"   ❌ Não consegui gerar a locução automática: {exc}")
        return False


def obter_duracao_midia(path):
    if not path or not os.path.exists(path) or not shutil.which("ffprobe"):
        return None

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


def gerar_video_sem_audio(vaga, output_path, duracao_seg, timeline_visual):
    total_frames = int(FPS * duracao_seg)
    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*'mp4v'),
        FPS,
        (600, 700)
    )

    if not writer.isOpened():
        raise RuntimeError("Não consegui iniciar o gravador de vídeo.")

    for fn in range(total_frames):
        t = fn / FPS

        if MOSTRAR_CARD_COMPLETO_INICIO and t < CARD_COMPLETO_INICIO_SEG:
            frame = render_frame(vaga, campos_visiveis_com_conteudo(vaga))
            writer.write(pil_to_cv2(frame))
            continue

        if MOSTRAR_CARD_COMPLETO_INICIO and t < (CARD_COMPLETO_INICIO_SEG + PISCADA_CARD_LIMPO_SEG):
            frame = render_frame(vaga, set())
            writer.write(pil_to_cv2(frame))
            continue

        visible = {f for f, st in timeline_visual if t >= st}

        fading, alpha = None, 1.0
        for field, start_t in timeline_visual:
            elapsed = t - start_t
            if 0 <= elapsed < FADE_DUR:
                fading, alpha = field, elapsed / FADE_DUR
                break

        if fading:
            frame = blend(
                render_frame(vaga, visible - {fading}),
                render_frame(vaga, visible),
                alpha
            )
        else:
            frame = render_frame(vaga, visible)

        writer.write(pil_to_cv2(frame))

    writer.release()


def juntar_audio_video(video_sem_audio, audio_path, video_final):
    if not shutil.which("ffmpeg"):
        return False

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_sem_audio,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        video_final,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def converter_video_sem_audio_para_h264(video_sem_audio, video_final):
    if not shutil.which("ffmpeg"):
        shutil.copyfile(video_sem_audio, video_final)
        return False

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_sem_audio,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        video_final,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        shutil.copyfile(video_sem_audio, video_final)
        return False


def gerar_video_final(vaga, video_final_path, video_sem_audio_path, audio_path, texto_locucao):
    audio_ok = gerar_audio_locucao(texto_locucao, audio_path)

    if audio_ok:
        dur_audio = obter_duracao_midia(audio_path)
        duracao_video = max(DURACAO_MIN_SEG, (dur_audio or DURACAO_MIN_SEG) + MARGEM_AUDIO_SEG)
    else:
        dur_audio = None
        duracao_video = DURACAO_MIN_SEG

    timeline_visual = calcular_timeline_visual(vaga, duracao_video)
    gerar_video_sem_audio(vaga, video_sem_audio_path, duracao_video, timeline_visual)

    if audio_ok:
        mux_ok = juntar_audio_video(video_sem_audio_path, audio_path, video_final_path)
        if not mux_ok:
            converter_video_sem_audio_para_h264(video_sem_audio_path, video_final_path)
    else:
        converter_video_sem_audio_para_h264(video_sem_audio_path, video_final_path)

    if not MANTER_VIDEO_SEM_AUDIO:
        try:
            os.remove(video_sem_audio_path)
        except OSError:
            pass


# ── MAIN ──────────────────────────────────────────────────────

def salvar_vagas_no_banco(vagas):
    """Insere as novas vagas no banco SQLite estruturando site e e-mail de forma separada."""
    db_path = "vagas_enfermagem.db"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Atualiza a estrutura para incluir a coluna de email se ela não existir
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
            email TEXT,
            link_edital TEXT,
            urgente INTEGER DEFAULT 0,
            atuacao TEXT
        );
    ''')
    conn.commit()

    # Código para adicionar a coluna 'email' se a tabela já existia sem ela
    try:
        cursor.execute("ALTER TABLE vagas ADD COLUMN email TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        # A coluna já existe, ignora o erro
        pass

    novas_inseridas = 0

    for vaga in vagas:
        estado = vaga.get('estado', '').strip()
        cidade = vaga.get('cidade', '').strip()
        cargo1 = vaga.get('cargo1', '').strip()
        cargo2 = vaga.get('cargo2', '').strip()
        cargo_completo = f"{cargo1} / {cargo2}" if cargo1 and cargo2 else (cargo1 or cargo2)

        instituicao = vaga.get('instituicao', '').strip()
        atuacao = vaga.get('atuacao', '').strip()
        link_site = vaga.get('link_site', '').strip()
        email = vaga.get('email', '').strip()

        prazo = "A definir"
        link_edital = ""
        urgente = 1 if "urgente" in atuacao.lower() else 0

        # Anti-duplicação
        cursor.execute('''
            SELECT id FROM vagas
            WHERE cargo = ? AND instituicao = ? AND cidade = ? AND estado = ?
        ''', (cargo_completo, instituicao, cidade, estado))

        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO vagas (cargo, instituicao, cidade, estado, prazo, link_inscricao, email, link_edital, urgente, atuacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cargo_completo, instituicao, cidade, estado, prazo, link_site, email, link_edital, urgente, atuacao))
            novas_inseridas += 1

    conn.commit()
    conn.close()

    if novas_inseridas > 0:
        print(f"💾 {novas_inseridas} nova(s) vaga(s) salva(s) no banco de dados SQLite!")
    else:
        print("ℹ️ Nenhuma vaga nova adicionada ao banco de dados.")


def atualizar_site_no_github():
    """Executa o push automático do arquivo index.html e do arquivo de logotipo ativo para o GitHub Pages."""
    try:
        # Adiciona o index.html gerado
        subprocess.run(["git", "add", "index.html"], check=True)
        
        # Procura por arquivos de logotipo comuns (logo-vagas-enfermagem.jpeg, logo.png, etc.) e os adiciona
        # Isso garante que se você trocar o arquivo localmente, o Git vai detectá-lo e subir junto
        for arquivo in os.listdir("."):
            if arquivo.startswith("logo") and arquivo.endswith((".png", ".jpg", ".jpeg", ".svg", ".gif")):
                subprocess.run(["git", "add", arquivo], check=True)
                print(f"📦 Logotipo detectado e adicionado ao commit: {arquivo}")

        # Prepara uma mensagem de commit com carimbo de data/hora atual
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        commit_msg = f"Atualização automática de vagas e logotipo: {timestamp}"
        
        # Faz o commit local
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        # Envia de forma silenciosa para o GitHub Pages usando o alias SSH que configuramos
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("🚀 Site e logotipo atualizados e publicados com sucesso no GitHub Pages!")

    except subprocess.CalledProcessError as e:
        print(f"❌ Falha ao atualizar o site no GitHub Pages (Erro no Git): {e}")
    except Exception as e:
        print(f"❌ Erro inesperado ao realizar o deploy: {e}")


def main():
    if not os.path.exists(CARD_BASE):
        print(f"❌ Arquivo '{CARD_BASE}' não encontrado na pasta.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(CSV_FILE):
        print(f"❌ '{CSV_FILE}' não encontrado.")
        return

    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        vagas = list(csv.DictReader(f))

    print(f"📋 {len(vagas)} vaga(s) encontrada(s)\n")

    try:
        salvar_vagas_no_banco(vagas)
    except Exception as e:
        print(f"⚠️ Erro ao salvar dados no banco de dados local: {e}")

    for i, vaga in enumerate(vagas, 1):
        estado = nome_arquivo_seguro(vaga.get('estado', ''))
        cidade = nome_arquivo_seguro(vaga.get('cidade', ''))
        base_nome = f"{i:02d}_{estado}_{cidade}"

        video_final_path = os.path.join(OUTPUT_DIR, f"{base_nome}.mp4")
        video_sem_audio_path = os.path.join(OUTPUT_DIR, f"{base_nome}_sem_audio.mp4")
        locucao_txt_path = os.path.join(OUTPUT_DIR, f"{base_nome}.txt")
        legenda_path = os.path.join(OUTPUT_DIR, f"{base_nome}_legenda_tiktok.txt")
        audio_path = os.path.join(OUTPUT_DIR, f"{base_nome}_locucao.mp3")

        print(f"🎬 [{i}/{len(vagas)}] {base_nome}.mp4")

        texto_locucao = gerar_texto_locucao(vaga, locucao_txt_path)
        gerar_texto_legenda_tiktok(vaga, legenda_path)
        gerar_video_final(vaga, video_final_path, video_sem_audio_path, audio_path, texto_locucao)

        print("   ✅ Vídeo final, locução, texto e legenda salvos!")

    print(f"\n🎉 Pronto! {len(vagas)} vídeo(s) gerado(s) em '{OUTPUT_DIR}/'")

    # Deploy estático automático
    if os.path.exists("gerar_estatico.py"):
        print("\n🌐 Iniciando atualização automática do site no GitHub Pages...")
        # 1. Gera o HTML atualizado do banco de dados local
        subprocess.run(["python3", "gerar_estatico.py"], check=True)
        # 2. Faz o commit e push do index.html gerado
        atualizar_site_no_github()
    else:
        print("\n⚠️  O arquivo 'gerar_estatico.py' não foi encontrado nesta pasta.")

if __name__ == "__main__":
    main()
