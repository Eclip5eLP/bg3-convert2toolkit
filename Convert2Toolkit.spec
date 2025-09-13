# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Convert2Toolkit.py'],
    pathex=[],
    binaries=[],
    datas=[('lib', 'lib')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='Convert2Toolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='lib/res/convert.ico'
)

import shutil

shutil.copyfile('settings.json', '{0}/settings.json'.format(DISTPATH))
shutil.copyfile('db.json', '{0}/db.json'.format(DISTPATH))