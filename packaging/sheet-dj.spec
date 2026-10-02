# PyInstaller spec: one folder holding a windowless sheet-dj.exe.
#
#     pyinstaller --noconfirm packaging/sheet-dj.spec      (from the repository root)
#
# The same exe is the icon's launcher and, run with --serve, the server (see launcher.py).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)  # noqa: F821  (PyInstaller provides SPECPATH)

# music21 imports many modules by name and ships data files (its corpus index, its XML schemas);
# neither is found by following imports.
hiddenimports = collect_submodules("music21")
datas = collect_data_files("music21") + collect_data_files("sheet_dj")

a = Analysis(  # noqa: F821
    [str(HERE / "entry.py")],
    pathex=[str(HERE.parent / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="sheet-dj",
    console=False,  # no console window, ever
    icon=str(HERE / "sheet-dj.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="sheet-dj")  # noqa: F821
