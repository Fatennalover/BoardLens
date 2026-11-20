"""Verified optional model data and user-supplied UCI installations."""
from pathlib import Path
import json
import os
import platform
import sys
import shutil
import subprocess

from .core import data_dir

GAIA_RELEASE='https://github.com/jromang/gaiachess/releases/download/v4.4.3/'
GAIA_ASSETS={
    ('Darwin','arm64'):('gaiachess-macos-apple-silicon','7a3a3b54ef2524985d0e68f538f994949eae62b4f13fadcd9c166bd509c002bf'),
    ('Windows','amd64'):('gaiachess-windows-console.exe','6808234a7a00e938ad099659e549027a0a843d9c9af47dd39d2ea578cc588c4f'),
    ('Linux','x86_64'):('gaiachess-linux-universal','8c0cec811a8f880e1ef763f42911c2bdf5d21b9a94378e35730dff1ae1615509'),
    ('Linux','aarch64'):('gaiachess-linux-neon','da2a9a0188fb8bd3d5eadcd8fb231bfd27aee768b006496f087c056b6c63a420'),
}
MAIA_URL='https://raw.githubusercontent.com/CSSLab/maia-chess/749204cf5979ce7f8b0412e804a4ee7c83c49ff8/maia_weights/'
MAIA_HASHES=(
 'e1cf1cd0c96b8a4fa6a275f4b9fd54ed1ffebf9fe44641b9fceded310e9619c4',
 'ead4ba953f233ae732999ebc1e2b675378148527ebcfad2f0acbc5e4c224d98e',
 '36195f87bf4761834baa0bf87472b18509a7261a9d7d6f1a8443261369a733f2',
 'd5353ea6766356dad2d28920c6692f37a5f30963767f1a3105d33b4d0af011e8',
 '35ab6f20421d59e1df3b17c5a5016947af4c6761368ef84044a9a9c7619a9a00',
 'd2c9e5948581acf4b9fc0b1e720c5dc0fe64ce80cfc4a239d3f8a42e1176c876',
 'd277eacd792d340a30abb464dc65127254e65cac57abca17facc469889b96478',
 '0031ad7c4256b1fd09fbebd28418d644d68b26cd2a45df4967ccf5c7ec9c4965',
 'e2f565f42d7cd9f122557e6dc4eb84e5bbaedceda1d404dc485d3611c7c97a12',
)
NEURAL_URL='https://raw.githubusercontent.com/pbaer/neural-chess/524ba14d4af3b739cbe19bd8cd0b14892e6305ca/viz/public/weights/v3.1-nano/'
NEURAL_FILES={
    'capsule.json':'0bf71c37aed4d7259a9db371d381763a64e7dec718f605ded0c1f58e8896ad5e',
    'weights.bin':'5b584935b8a23a662096d2ecc34f2af8c580058252ef0567194b080187945468',
}
IMPORTS={
    'toby':'https://github.com/Yosha87/Toby#download',
    'rodent':'https://www.chessengeria.eu/post/final-rodent-review',
}


def folder(entry):
    return data_dir()/'engine-addons'/entry.identity


def imported(entry):
    try:
        path=Path(json.loads((folder(entry)/'executable.json').read_text())['path'])
        if path.is_file():return path
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return None


def verify_executable(command, kind):
    import chess.engine
    from .engine import uci_process_options
    with chess.engine.SimpleEngine.popen_uci(command, timeout=35, **uci_process_options(command)) as engine:
        if kind == 'toby' and 'Precision' in engine.options:
            engine.configure({'Precision': 'Fast'})
        board=chess.Board()
        result=engine.play(board,chess.engine.Limit(time=.15))
        if result.move not in board.legal_moves:raise ValueError('The executable returned no legal test move.')


def set_import(entry,path):
    path=Path(path).resolve()
    verify_executable(str(path), entry.kind)
    target=folder(entry)/'executable.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'path':str(path)}))


def allie_python():
    return data_dir()/'allie-runtime'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def available(entry):
    from . import lc0_support
    if imported(entry):return True
    base=folder(entry)
    if entry.kind in ('rodent', 'toby'):
        from .managed_engines import installed
        return installed(entry.kind, base)
    if entry.kind=='gaia':return (base/('gaia.exe' if os.name=='nt' else 'gaia')).is_file()
    if entry.kind=='maia1':return lc0_support.available() and (base/f'maia-{entry.rating}.pb.gz').is_file()
    if entry.kind=='allie':return allie_python().is_file() and (base/'ready').is_file()
    if entry.kind=='neural':return all((base/f).is_file() for f in NEURAL_FILES)
    return False


def install(entry):
    from .engine_library import fetch
    from . import lc0_support
    base=folder(entry)
    if entry.kind=='gaia':
        choice=GAIA_ASSETS.get((platform.system(),platform.machine().lower()))
        if not choice:raise ValueError('Use Import executable for a compatible Gaia build.')
        name,sha=choice
        target=base/('gaia.exe' if os.name=='nt' else 'gaia')
        fetch(GAIA_RELEASE+name,target,'sha256',sha)
        target.chmod(0o755)
    elif entry.kind=='maia1':
        if not lc0_support.available():lc0_support.install()
        name=f'maia-{entry.rating}.pb.gz'
        fetch(MAIA_URL+name,base/name,'sha256',MAIA_HASHES[(entry.rating-1100)//100])
    elif entry.kind=='allie':
        from .runtime_setup import create_runtime
        expected=22_000_000_000 if entry.identity.endswith('2.1') else 15_000_000_000
        if shutil.disk_usage(data_dir()).free<expected:
            raise ValueError(f'Free about {expected//1_000_000_000} GB to install this Allie model.')
        create_runtime(data_dir()/'allie-runtime')
        base.mkdir(parents=True,exist_ok=True)
        python=allie_python()
        with (base/'install.log').open('a') as log:
            subprocess.run([str(python),'-m','pip','install','torch','transformers','python-chess','huggingface_hub'],
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
            subprocess.run([str(python),str(Path(__file__).with_name('allie_uci.py')),entry.identity,str(base),'--download'],
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=14400)
        (base/'ready').touch()
    elif entry.kind=='neural':
        for name,sha in NEURAL_FILES.items():fetch(NEURAL_URL+name,base/name,'sha256',sha)
    elif entry.kind in ('rodent', 'toby'):
        from .managed_engines import install as install_managed
        install_managed(entry.kind, base)
    else:
        raise ValueError('Download and unpack the upstream engine, then choose Import executable.')


def command(entry):
    from . import lc0_support
    path=imported(entry)
    if path:return [str(path),'--no-gui'] if entry.kind=='gaia' else str(path)
    base=folder(entry)
    if entry.kind in ('rodent', 'toby'):
        from .managed_engines import command as managed_command
        return managed_command(entry.kind, base / 'managed')
    if entry.kind=='gaia':return [str(base/('gaia.exe' if os.name=='nt' else 'gaia')),'--no-gui']
    if entry.kind=='maia1':
        args=lc0_support.command()
        args[1]='--weights='+str(base/f'maia-{entry.rating}.pb.gz')
        return args
    if entry.kind=='allie':return [str(allie_python()),str(Path(__file__).with_name('allie_uci.py')),entry.identity,str(base)]
    if entry.kind=='neural':
        python=os.environ.get('BOARDLENS_NATIVE_PYTHON') or sys.executable
        return [python,str(Path(__file__).with_name('neural_uci.py')),str(base)]
    raise ValueError('Import the engine executable first.')
