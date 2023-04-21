# ------------------------------------------------------------
# Robust path handling – works for both PyInstaller 5 & 6
# ------------------------------------------------------------
from pathlib import Path
import sys, os, PySide6, html     # keep existing imports

# PyInstaller ≥ 6 gives a directory; < 6 gives a file.  sys.argv[0] is a file.
raw_path = Path(globals().get("SPECPATH", sys.argv[0])).resolve()

if raw_path.is_dir():                 # PyInstaller 6
    SPEC_DIR      = raw_path                     # …/scripts
    SPEC_FILE     = SPEC_DIR / "freeze.spec"
else:                                  # PyInstaller≤5 or fallback
    SPEC_FILE     = raw_path                     # …/scripts/freeze.spec
    SPEC_DIR      = SPEC_FILE.parent

PROJECT_ROOT = SPEC_DIR.parent                    # …/promptbuilder
ENTRY_POINT  = PROJECT_ROOT / "promptbuilder" / "main.py"

print(f"SPEC_DIR      = {SPEC_DIR}")
print(f"PROJECT_ROOT  = {PROJECT_ROOT}")
print(f"ENTRY_POINT   = {ENTRY_POINT}")

if not ENTRY_POINT.is_file():
    sys.exit(f"ERROR: entry‑point not found → {ENTRY_POINT}")


block_cipher = None

# --- Application Details ---
APP_NAME = "PromptBuilder"
# Use PROJECT_ROOT to build asset paths
ICON_PATH_OBJ = PROJECT_ROOT / "assets" / "icon.ico"
ICON_PATH = str(ICON_PATH_OBJ) if ICON_PATH_OBJ.exists() else None

# --- Find PySide6 directory ---
try:
    pyside6_dir = Path(PySide6.__path__[0])
    print(f"Found PySide6 directory: {pyside6_dir}")
except Exception as e:
    print(f"Error finding PySide6 directory: {e}")
    pyside6_dir = None

# --- Data Files ---
datas = []
# Use PROJECT_ROOT to build asset paths
assets_dir = PROJECT_ROOT / "assets"
if assets_dir.is_dir():
    datas += [(str(assets_dir / "*"), "assets")]
    print(f"Including data files from: {assets_dir}")
else:
    print(f"Warning: Assets directory not found at {assets_dir}")

# --- Hidden Imports & Excludes ---
hiddenimports = [
    'PySide6.QtSvg', 'PySide6.QtNetwork', 'PySide6.QtGui',
    'PySide6.QtCore', 'PySide6.QtWidgets',
    'loguru', 'pydantic', 'tiktoken', 'html', 'fnmatch',
    'threading', 'mmap', 'time', 'importlib.metadata', 'patch',
    'tiktoken_ext.openai_public', 'tiktoken_ext'
]
excludes = ['tests', 'pytest']

# --- Binaries ---
binaries = []
if pyside6_dir and pyside6_dir.is_dir():
    qt_plugin_dirs = ['platforms', 'styles', 'imageformats', 'iconengines']
    for plugin_dir in qt_plugin_dirs:
        src_path = pyside6_dir / 'plugins' / plugin_dir
        if src_path.is_dir(): binaries += [(str(src_path), f'PySide6/plugins/{plugin_dir}')]; print(f"Including Qt plugin directory: {src_path} -> PySide6/plugins/{plugin_dir}")
        else: print(f"Warning: Qt plugin source directory not found: {src_path}")
    svg_dll_path = pyside6_dir / 'Qt6Svg.dll'
    if svg_dll_path.is_file(): binaries += [(str(svg_dll_path), '.')]; print(f"Including Qt6Svg.dll: {svg_dll_path} -> ./")
    else: print(f"Warning: Qt6Svg.dll not found at {svg_dll_path}")
else: print("Warning: PySide6 directory not found, cannot include Qt plugins/DLLs automatically.")


# --- Analysis Phase ---
a = Analysis(
    [str(ENTRY_POINT)],          # Pass entry point as string
    pathex=[str(PROJECT_ROOT)],  # Pass project root as string
    binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=excludes, win_no_prefer_redirects=False,
    win_private_assemblies=False, cipher=block_cipher, noarchive=False,
)

# --- PYZ Archive ---
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- Executable ---
exe = EXE(
    pyz, a.scripts, [], a.binaries, a.zipfiles, a.datas,
    name=APP_NAME, debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, upx_exclude=[], runtime_tmpdir=None, console=True, # <-- CHANGE HERE
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=ICON_PATH # Pass icon path as string or None
)