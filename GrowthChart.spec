# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('data', 'data'), ('zscore', 'zscore'), ('api', 'api'), ('clinical', 'clinical'), ('importers', 'importers'), ('exports', 'exports')],
    hiddenimports=['flask', 'flask_cors', 'jinja2', 'werkzeug', 'markupsafe', 'itsdangerous', 'blinker', 'click', 'bidi', 'bidi.algorithm', 'arabic_reshaper', 'pdfplumber', 'pdfminer', 'pdfminer.high_level', 'pdfminer.layout', 'openpyxl', 'reportlab', 'PIL', 'PIL.Image', 'sqlite3'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GrowthChart',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GrowthChart',
)
