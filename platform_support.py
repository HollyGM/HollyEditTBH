"""Caminhos, abertura de pastas e fonte de interface por sistema operacional.

Até a 3.4.0 o editor assumia Windows em três pontos que quebravam calado fora
dele: a pasta do save era montada como ``~/AppData/LocalLow/...`` mesmo no Linux
e no macOS, ``os.startfile`` só existe no Windows (chamá-lo em outro sistema
levanta ``AttributeError``) e ``LOCALAPPDATA`` decidia onde gravar cache e
ícones. Este módulo concentra essas três decisões e não importa ``tkinter``,
para poder ser testado sem interface gráfica.

A descoberta do save no Linux passa pelas bibliotecas Steam declaradas em
``libraryfolders.vdf``, e não só pelas pastas dentro do ``$HOME``: uma biblioteca
em disco externo é comum e antes ficava invisível para o editor.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app_meta import STEAM_APP_ID, STEAM_PLAYTEST_APP_ID

#: Subcaminho do jogo dentro da pasta de dados da Unity, igual em toda plataforma.
GAME_VENDOR = "TesseractStudio"
GAME_FOLDER = "TaskbarHero"
SAVE_FILE_NAME = "SaveFile_Live.es3"

#: AppIDs procurados em ``compatdata``, na ordem de preferência: o jogo publicado
#: vence o playtest mesmo quando os dois prefixos existem.
STEAM_APP_IDS = (STEAM_APP_ID, STEAM_PLAYTEST_APP_ID)

#: ``libraryfolders.vdf`` real tem alguns KB; o teto evita carregar um arquivo
#: gigante para a memória se o caminho apontar para outra coisa.
VDF_READ_LIMIT = 1024 * 1024

#: O VDF é um formato de pares aspeados. Uma regex sobre as linhas ``"path"``
#: resolve sem trazer uma dependência nova para um projeto que hoje só usa
#: ``cryptography`` — e ainda assim de forma opcional.
_VDF_PATH_RE = re.compile(r'"path"\s*"([^"]*)"', re.IGNORECASE)

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


def _default_steam_roots(home: Path) -> list[Path]:
    """Instalações Steam do próprio usuário: pacote do sistema, nativa e Flatpak."""
    return [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    ]


def _library_paths_from_vdf(vdf_file: Path) -> list[Path]:
    """Bibliotecas declaradas em ``libraryfolders.vdf``.

    Nunca levanta exceção. ``legacy_editor`` resolve ``GAME_SAVE_DIR`` em tempo de
    import, então um disco desmontado, um arquivo sem permissão de leitura ou um
    VDF corrompido derrubariam a aplicação na inicialização em vez de apenas não
    encontrarem o save.
    """
    try:
        with vdf_file.open("rb") as handle:
            blob = handle.read(VDF_READ_LIMIT)
    except (OSError, ValueError):
        return []
    content = blob.decode("utf-8", errors="replace")
    found: list[Path] = []
    for raw in _VDF_PATH_RE.findall(content):
        # O Steam grava o separador escapado no formato Windows ("D:\\Jogos").
        cleaned = raw.replace("\\\\", "\\").strip()
        if not cleaned:
            continue
        try:
            found.append(Path(cleaned))
        except (OSError, ValueError):
            continue
    return found


def steam_library_roots(home: Path) -> list[Path]:
    """Raízes de biblioteca Steam: as padrão do usuário mais as do ``libraryfolders.vdf``.

    Sem ler o VDF, uma biblioteca em disco externo — a configuração de quem tem
    SSD de sistema pequeno e joga a partir de outro disco — fica invisível para o
    editor, mesmo com o AppID correto.
    """
    libraries: list[Path] = []
    seen: set[str] = set()

    def remember(path: Path) -> None:
        marker = str(path)
        if marker not in seen:
            seen.add(marker)
            libraries.append(path)

    for root in _default_steam_roots(home):
        remember(root)
    # Só as raízes padrão são varridas: ``~/.steam/steam`` costuma ser symlink
    # para ``~/.local/share/Steam``, então o mesmo VDF apareceria duas vezes, e
    # revarrer as bibliotecas declaradas abriria caminho para recursão entre
    # instalações que se apontam mutuamente.
    for root in list(libraries):
        for declared in _library_paths_from_vdf(root / "steamapps" / "libraryfolders.vdf"):
            remember(declared)
    return libraries


def _proton_prefix_roots(home: Path) -> list[Path]:
    """Prefixos Proton/Wine onde uma instalação Windows do jogo pode estar."""
    libraries = steam_library_roots(home)
    # AppID no laço externo: o prefixo do jogo publicado vence o do playtest
    # mesmo quando os dois existem, em bibliotecas diferentes.
    roots = [
        library / "steamapps" / "compatdata" / str(app_id) / "pfx" / "drive_c"
        for app_id in STEAM_APP_IDS
        for library in libraries
    ]
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
    """Prefere uma pasta com save a um prefixo vazio de outra instalação.

    Devolver a canônica em vez de ``None`` mantém o comportamento histórico:
    a interface só usa este caminho como diretório inicial do seletor e como
    alvo do botão "Abrir pasta do save", ambos já tolerantes a ausência.
    """
    candidates = game_save_dir_candidates(home, platform)
    for candidate in candidates:
        try:
            if (candidate / SAVE_FILE_NAME).is_file():
                return candidate
        except OSError:
            continue
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return candidates[0]


def posix_game_is_running_fail_safe() -> bool:
    """Detecta o jogo nativo ou sob Wine/Proton; falha de consulta bloqueia salvar.

    Só inspeciona argumentos de executáveis Wine conhecidos. Procurar o nome
    em qualquer linha de comando também confundiria editores, scripts e testes
    que apenas mencionam o jogo com o próprio processo do jogo.
    """
    try:
        result = subprocess.run(
            ["/bin/ps", "-A", "-ww", "-o", "comm=", "-o", "args="],
            capture_output=True, text=True, errors="replace", timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if result.returncode != 0 or not result.stdout.strip():
        return True
    game_names = {"taskbarhero", "taskbarhero.exe", "taskbarhero.x86_64"}
    wine_names = {"wine", "wine64", "wine-preloader", "wine64-preloader", "start.exe"}
    game_path = re.compile(
        r"(?:^|[/\\\s\"'])taskbarhero(?:\.exe|\.x86_64)?(?=$|[\s\"'])", re.IGNORECASE
    )
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if not parts:
            continue
        name = re.split(r"[/\\]", parts[0])[-1].casefold()
        if name in game_names:
            return True
        if name in wine_names and len(parts) > 1 and game_path.search(parts[1]):
            return True
    return False


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
