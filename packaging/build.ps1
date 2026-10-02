# Build the Windows installer: build\installer\sheet-dj-setup-<version>.exe
#
# Run from the repository root, in a Python 3.12 environment with the project and the build extra:
#     pip install -e ".[build]"
#     powershell -File packaging\build.ps1
#
# Needs Inno Setup 6 (iscc.exe) on the PATH or in its default folder.

$ErrorActionPreference = "Stop"

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { throw "Could not read the version from pyproject.toml" }

pyinstaller --noconfirm --distpath build\dist --workpath build\work packaging\sheet-dj.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

python packaging\smoke_test.py build\dist\sheet-dj\sheet-dj.exe
if ($LASTEXITCODE -ne 0) { throw "The packaged program failed its smoke test" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$version" packaging\sheet-dj.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
