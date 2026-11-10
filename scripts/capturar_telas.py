"""Captura telas do painel para o README (docs/imagens/) e monta um GIF de apresentação.

Pré-requisitos: requirements-dev.txt instalado, `python -m playwright install chromium`
e o painel rodando (padrão: http://localhost:8501).

Uso:
    python scripts/capturar_telas.py
    python scripts/capturar_telas.py --url http://localhost:8766
"""

import argparse
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "imagens"

# (caminho da página, arquivo, seletor CSS e quantidade mínima para considerar carregada)
PAGINAS = [
    ("", "01_visao_geral.png", ".js-plotly-plot", 3),
    ("inflacao_juros", "02_inflacao_juros.png", ".js-plotly-plot", 4),
    ("comparador", "03_comparador.png", '[data-testid="stDataFrame"]', 2),
    ("alertas", "04_alertas.png", ".js-plotly-plot", 1),
    ("mercado", "05_mercado.png", ".js-plotly-plot", 2),
    ("cambio", "06_cambio.png", ".js-plotly-plot", 2),
]
LARGURA, ALTURA = 1440, 900


def capturar(url_base: str) -> list[Path]:
    """Abre cada página num Chromium sem janela e salva a parte visível (1440 x 900)."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivos = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(
            viewport={"width": LARGURA, "height": ALTURA}, color_scheme="dark", locale="pt-BR"
        )
        for caminho, nome, seletor, minimo in PAGINAS:
            pagina.goto(f"{url_base.rstrip('/')}/{caminho}")
            pagina.wait_for_selector('[data-testid="stMainBlockContainer"]', timeout=60_000)
            pagina.wait_for_function(
                f"document.querySelectorAll('{seletor}').length >= {minimo}", timeout=60_000
            )
            pagina.wait_for_timeout(2_500)  # animações e fontes
            arquivo = DESTINO / nome
            pagina.screenshot(path=str(arquivo))
            arquivos.append(arquivo)
            print(f"ok {arquivo.relative_to(RAIZ)}")
        navegador.close()
    return arquivos


def montar_gif(imagens: list[Path], destino: Path, largura: int = 1100) -> Path:
    """GIF em loop com as capturas (2,8 s por tela), reduzido para ficar leve no README."""
    quadros = []
    for caminho in imagens:
        imagem = Image.open(caminho).convert("RGB")
        altura = round(imagem.height * largura / imagem.width)
        reduzida = imagem.resize((largura, altura), Image.Resampling.LANCZOS)
        quadros.append(reduzida.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    quadros[0].save(
        destino, save_all=True, append_images=quadros[1:], duration=2_800, loop=0, optimize=True
    )
    print(f"ok {destino.relative_to(RAIZ)} ({destino.stat().st_size / 1024:.0f} KB)")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description="Captura telas do painel para o README.")
    parser.add_argument("--url", default="http://localhost:8501", help="endereço do painel")
    args = parser.parse_args()
    imagens = capturar(args.url)
    montar_gif(imagens, DESTINO / "painel.gif")


if __name__ == "__main__":
    main()
