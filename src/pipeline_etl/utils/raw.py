"""Arquivos da camada raw: listagem em ordem de extração e nova versão no mesmo dia.

O raw nunca é sobrescrito. A primeira extração do dia grava `<nome>.json`; extrações
seguintes no mesmo dia (ex.: botão "Atualizar dados" do painel) gravam
`<nome>__HHMMSS.json` na mesma partição. A ordem alfabética dentro da partição é a
ordem de extração ("." vem antes de "_"), então "o último arquivo" é sempre o mais novo.
"""

from datetime import datetime
from pathlib import Path

SEPARADOR_VERSAO = "__"
PREFIXO_PARTICAO = "data_extracao="


def listar_arquivos(pasta_fonte: Path, nome_base: str) -> list[Path]:
    """Todos os arquivos de dados `nome_base` (sem os .meta.json), da extração mais antiga
    para a mais recente: partição por data e, dentro dela, versão por horário."""
    padroes = [f"{nome_base}.json", f"{nome_base}{SEPARADOR_VERSAO}*.json"]
    arquivos = {
        arquivo
        for padrao in padroes
        for arquivo in pasta_fonte.glob(f"{PREFIXO_PARTICAO}*/{padrao}")
        if not arquivo.name.endswith(".meta.json")
    }
    return sorted(arquivos)


def arquivo_para_gravar(
    pasta_particao: Path, nome_base: str, nova_versao: bool, agora: datetime | None = None
) -> Path | None:
    """Caminho do arquivo a gravar hoje, ou None se já existe e não se pediu nova versão."""
    base = pasta_particao / f"{nome_base}.json"
    if not base.exists():
        return base
    if not nova_versao:
        return None
    agora = agora or datetime.now()
    versao = pasta_particao / f"{nome_base}{SEPARADOR_VERSAO}{agora:%H%M%S}.json"
    if versao.exists():  # duas atualizações no mesmo segundo
        raise FileExistsError(f"{versao} já existe; raw não é sobrescrito")
    return versao


def caminho_meta(arquivo: Path) -> Path:
    """Arquivo de metadados ao lado do arquivo de dados: x.json -> x.meta.json."""
    return arquivo.with_name(arquivo.name.removesuffix(".json") + ".meta.json")
