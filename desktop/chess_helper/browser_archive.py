"""Export the bundled browser extension without revealing an installation path."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

FILES = (
    "manifest.json", "background.js", "reader.js", "content.js",
    "coach.js", "popup.html", "popup.js", "README.txt",
)


def bundled_extension():
    return Path(__file__).resolve().parents[1] / "BrowserReader"


def write_archive(destination, source=None):
    folder = Path(source) if source is not None else bundled_extension()
    if not all((folder / name).is_file() for name in FILES):
        raise FileNotFoundError("The complete Browser Reader is missing from this build.")
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.writestr(f"BrowserReader/{name}", (folder / name).read_bytes())
