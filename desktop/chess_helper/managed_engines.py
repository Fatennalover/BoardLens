"""Verified desktop installers for Rodent IV and Toby."""
import os
import platform
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .core import data_dir, find_engine


RODENT_REV = 'e8d84c8c8c189a1cf4eb27c578fc573af3b916d2'
RODENT_HASH = '5d35c65bfccd58fe74a73b58434ec1542f4aabc45b343163b277870c681f7773'
TOBY_REV = 'b3b4e0faa1a7931578ad375219dc0b44b5ac12d6'
TOBY_HASH = '51dfaaa72862f0c6cb607c4c24a22142f1e6b97cd39e8b0d7edd7ee27956c65a'
TOBY_PACKAGES = {
    'Windows': ('Toby-light-2026-11-13.zip', 'd08e0f61b701e23b740aa6bab115057d2900887de6cd2c475bdad7b16ff45377'),
    'Linux': ('Toby-linux-light-2026-11-13.zip', 'e7d7a625d27b2cbf42ba1d167e8bf30f4e1b4c2eb5165372c79c20c38990067f'),
}


def can_download(kind):
    system = platform.system()
    if kind == 'rodent':
        return system in ('Darwin', 'Linux')
    return system == 'Darwin' or (
        system in TOBY_PACKAGES and platform.machine().lower() in ('x86_64', 'amd64')
    )


def unpack(archive, destination):
    with ZipFile(archive) as source:
        if sum(member.file_size for member in source.infolist()) > shutil.disk_usage(destination).free:
            raise ValueError('Free more disk space to unpack the engine.')
        for member in source.infolist():
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (name.is_absolute() or '..' in name.parts or '\\' in member.filename
                    or ':' in member.filename or stat.S_ISLNK(mode)):
                raise ValueError('The engine archive contains an unsupported file path.')
            target = destination.joinpath(*name.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as content, target.open('xb') as output:
                shutil.copyfileobj(content, output)
            if os.name != 'nt' and mode & 0o111:
                target.chmod(0o755)


def prepare_rodent(archive, staging):
    from .engine_library import fetch

    system = platform.system()
    if system == 'Darwin':
        tools = subprocess.run(['/usr/bin/xcode-select', '-p'], capture_output=True, text=True)
        if tools.returncode or not Path(tools.stdout.strip()).is_dir():
            raise ValueError('Rodent needs Apple’s Command Line Tools for its native build. Run xcode-select --install, then retry.')
        compiler = ['/usr/bin/xcrun', '--sdk', 'macosx', 'clang++']
    else:
        native = shutil.which('g++') or shutil.which('clang++')
        if not native:
            raise ValueError('Rodent needs a C++ compiler. Install g++ or clang++ with your Linux package manager.')
        compiler = [native]
    fetch(f'https://codeload.github.com/nescitus/rodent-iv/zip/{RODENT_REV}', archive, 'sha256', RODENT_HASH)
    unpack(archive, staging)
    root = staging / f'rodent-iv-{RODENT_REV}'
    sources = sorted(str(source.relative_to(root)) for source in (root / 'sources/src').glob('*.cpp'))
    result = subprocess.run(
        [*compiler, '-std=c++14', '-O3', '-DNDEBUG', '-DNO_THREADS',
         '-fno-strict-aliasing', '-fwrapv', *sources, '-o', 'rodentIV'],
        capture_output=True, text=True, cwd=root, timeout=180,
    )
    if result.returncode:
        raise ValueError('Rodent build failed. ' + (result.stderr.strip().splitlines() or ['Check the C++ toolchain.'])[-1])
    # Rodent looks for opening books and personalities beside its executable.
    for book in ('guide.bin', 'rodent.bin'):
        shutil.copy2(root / 'exe' / book, root / 'books' / book)
    return root


def maia_checkpoint():
    cache = data_dir() / 'maia3-cache'
    return next(iter(sorted(cache.glob('hub/models--UofTCSSLab--Maia3-79M/snapshots/*/maia3-79m.pt'))), None)


def toby_command(root):
    if platform.system() != 'Darwin':
        return str(root / ('toby.exe' if os.name == 'nt' else 'toby'))
    from .engine_config import maia_python

    checkpoint, stockfish = maia_checkpoint(), find_engine()
    if not checkpoint or not stockfish or not maia_python().is_file():
        raise ValueError('Toby needs the Maia-3 79M model, its Python runtime and Stockfish.')
    return [str(maia_python()), str(Path(__file__).with_name('toby_launcher.py')),
            str(root / 'toby_uci.py'), str(checkpoint), stockfish]


def prepare_toby(archive, staging):
    from .engine_library import BY_ID, available, fetch, install

    system = platform.system()
    if system == 'Darwin':
        if not available(BY_ID['stockfish']):
            install('stockfish')
        if not available(BY_ID['maia3-79m']):
            install('maia3-79m')
        fetch(f'https://codeload.github.com/Yosha87/Toby/zip/{TOBY_REV}', archive, 'sha256', TOBY_HASH)
        unpack(archive, staging)
        return staging / f'Toby-{TOBY_REV}'
    name, checksum = TOBY_PACKAGES[system]
    fetch(f'https://toby.tribychess.org/{name}', archive, 'sha256', checksum)
    unpack(archive, staging)
    return staging / 'Toby'


def command(kind, root):
    return toby_command(root) if kind == 'toby' else str(root / 'rodentIV')


def installed(kind, folder):
    root = folder / 'managed'
    if not (root / '.boardlens-verified').is_file():
        return False
    try:
        launch = command(kind, root)
    except ValueError:
        return False
    return all(Path(file).is_file() for file in launch) if isinstance(launch, list) else Path(launch).is_file()


def install(kind, folder):
    from .engine_addons import verify_executable

    if not can_download(kind):
        raise ValueError('Import an executable built for this computer.')
    folder.mkdir(parents=True, exist_ok=True)
    minimum = 2_500_000_000 if kind == 'toby' and platform.system() != 'Darwin' else 170_000_000
    if shutil.disk_usage(folder).free < minimum:
        raise ValueError(f'Free at least {minimum // 1_000_000} MB to download and unpack this engine.')
    target = folder / 'managed'
    if installed(kind, folder):
        return
    with tempfile.TemporaryDirectory(prefix='install-', dir=folder) as temporary:
        staging = Path(temporary)
        prepare = prepare_toby if kind == 'toby' else prepare_rodent
        root = prepare(staging / 'download.zip', staging)
        verify_executable(command(kind, root), kind)
        (root / '.boardlens-verified').touch()
        if target.exists():
            target.rename(staging / 'previous')
        try:
            root.rename(target)
        except OSError:
            if (staging / 'previous').exists():
                (staging / 'previous').rename(target)
            raise
