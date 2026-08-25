"""Caminhos, abertura de pastas e fonte de interface por sistema operacional.

Até a 3.4.0 o editor assumia Windows em três pontos que quebravam calado fora
dele: a pasta do save era montada como ``~/AppData/LocalLow/...`` mesmo no Linux
e no macOS, ``os.startfile`` só existe no Windows (chamá-lo em outro sistema
levanta ``AttributeError``) e ``LOCALAPPDATA`` decidia onde gravar cache e
ícones. Este módulo concentra essas três decisões e não importa ``tkinter``,
para poder ser testado sem interface gráfica.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Subcaminho do jogo dentro da pasta de dados da Unity, igual em toda plataforma.
GAME_VENDOR = "TesseractStudio"
GAME_FOLDER = "TaskbarHero"
SAVE_FILE_NAME = "SaveFile_Live.es3"

#: AppID do Taskbar Hero na Steam, usado para achar o prefixo Proton no Linux.
STEAM_APP_ID = "2957000"

#: Ordem de preferência de fonte por sistema. A primeira família realmente
#: instalada vence; sem nenhuma delas o Tk decide sozinho.
FONT_PREFERENCES = {
    "win32": ("Segoe UI Variable Text", "Segoe UI", "Tahoma"),
    "darwin": ("SF Pro Text", "Helvetica Neue", "Lucida Grande"),
    "linux": ("Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Liberation Sans"),
}
FONT_FALLBACKS = ("Segoe UI", "Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial", "Helvetica")


def current_platform(platform: str | None = None) -> str:
    """Normaliza ``sys.platform`` para as três famílias que o editor reconhece."""
    value = (platform or sys.platform).lower()
    if value.startswith("win"):
        return "win32"
    if value == "darwin":
        return "darwin"
    return "linux"


def _unity_data_root(home: Path, platform: str) -> Path:
    """Raiz onde a Unity grava ``persistentDataPath`` em cada sistema."""
    if platform == "win32":
        return home / "AppData" / "LocalLow"
    if platform == "darwin":
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))


def _proton_prefix_roots(home: Path) -> list[Path]:
    """Prefixos Proton/Wine onde uma instalação Windows do jogo pode estar."""
    libraries = [
        home / ".steam" / "steam" / "steamapps",
        home / ".local" / "share" / "Steam" / "steamapps",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam" / "steamapps",
    ]
    roots = [library / "compatdata" / STEAM_APP_ID / "pfx" / "drive_c" for library in libraries]
    roots.append(home / ".wine" / "drive_c")
    users = []
    for root in roots:
        users.append(root / "users" / "steamuser" / "AppData" / "LocalLow")
        users.append(root / "users" / os.environ.get("USER", "steamuser") / "AppData" / "LocalLow")
    return users


def game_save_dir_candidates(home: Path | None = None, platform: str | None = None) -> list[Path]:
    """Todos os locais plausíveis do save, do mais provável ao menos provável.

    No Linux e no macOS o jogo normalmente roda sob Proton/Wine ou Crossover, e
    nesse caso o save continua sob uma árvore ``AppData/LocalLow`` dentro do
    prefixo — por isso os prefixos entram na lista antes do caminho nativo.
    """
    base = Path(home) if home is not None else Path.home()
    system = current_platform(platform)
    suffix = Path(GAME_VENDOR) / GAME_FOLDER
    candidates: list[Path] = []
    if system == "win32":
        candidates.append(_unity_data_root(base, "win32") / suffix)
    elif system == "darwin":
        candidates.append(_unity_data_root(base, "darwin") / suffix)
        # Crossover/Wine no macOS mantém a árvore Windows dentro da garrafa.
        candidates.append(
            base / "Library" / "Application Support" / "CrossOver" / "Bottles" / "Steam"
            / "drive_c" / "users" / "crossover" / "AppData" / "LocalLow" / suffix
        )
        candidates.append(base / ".wine" / "drive_c" / "users" / base.name / "AppData" / "LocalLow" / suffix)
    else:
        candidates.extend(prefix / suffix for prefix in _proton_prefix_roots(base))
        candidates.append(_unity_data_root(base, "linux") / "unity3d" / suffix)
        candidates.append(_unity_data_root(base, "linux") / suffix)

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        marker = str(candidate)
        if marker not in seen:
            seen.add(marker)
            unique.append(candidate)
    return unique


def default_game_save_dir(home: Path | None = None, platform: str | None = None) -> Path:
    """Primeira pasta de save que existe; sem nenhuma, a canônica da plataforma.

    Devolver a canônica em vez de ``None`` mantém o comportamento histórico:
    a interface só usa este caminho como diretório inicial do seletor e como
    alvo do botão "Abrir pasta do save", ambos já tolerantes a ausência.
    """
    candidates = game_save_dir_candidates(home, platform)
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return candidates[0]


def user_data_dir(app_name: str, fallback: Path, frozen: bool = False, platform: str | None = None) -> Path:
    """Pasta gravável para cache e ícones quando o app roda empacotado.

    Fora do modo empacotado o editor continua usando a própria pasta do
    projeto (``fallback``), que é o que os testes e o desenvolvimento esperam.
    """
    if not frozen:
        return fallback
    system = current_platform(platform)
    if system == "win32":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root) / app_name if root else fallback
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    root = os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / app_name


def open_in_file_manager(path: str | os.PathLike[str], platform: str | None = None) -> bool:
    """Abre a pasta no gerenciador de arquivos do sistema.

    ``os.startfile`` não existe fora do Windows; usar o nome sem checar levantava
    ``AttributeError`` em vez de abrir coisa alguma. Devolve ``False`` quando
    nenhum abridor pôde ser acionado, para a interface poder avisar.
    """
    target = os.fspath(path)
    system = current_platform(platform)
    if system == "win32":
        opener = getattr(os, "startfile", None)
        if opener is None:
            return False
        try:
            opener(target)
            return True
        except OSError:
            return False
    command = "open" if system == "darwin" else "xdg-open"
    if shutil.which(command) is None:
        return False
    try:
        subprocess.Popen(
            [command, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def preferred_font_family(available: object, platform: str | None = None) -> str | None:
    """Melhor família de fonte instalada, ou ``None`` para deixar o Tk decidir.

    ``available`` é a coleção devolvida por ``tkinter.font.families()``; a
    comparação ignora caixa porque o Tk relata os nomes como o sistema os grafa.
    """
    try:
        installed = {str(name).casefold() for name in available or ()}
    except TypeError:
        return None
    if not installed:
        return None
    system = current_platform(platform)
    for family in (*FONT_PREFERENCES.get(system, ()), *FONT_FALLBACKS):
        if family.casefold() in installed:
            return family
    return None
