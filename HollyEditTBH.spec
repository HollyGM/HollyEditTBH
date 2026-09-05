# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento do HollyEditTBH para Windows, Linux e macOS.

O mesmo spec serve as três plataformas. As partes específicas do Windows
(recurso VERSIONINFO) e do macOS (bundle .app) ficam sob condição em vez de
serem passadas sempre: o PyInstaller ignora `version=` fora do Windows com um
aviso, e sem o BUNDLE o macOS receberia só um executável de terminal, sem
ícone no Dock nem integração com o Finder.
"""
import sys

IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'

datas = [
    ('tbh_items_cache.json', '.'),
    ('tbh_item_icons', 'tbh_item_icons'),
    ('hero_portraits', 'hero_portraits'),
    ('hero_profiles.json', '.'),
]

a = Analysis(
    ['hollyedittbh_final.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HollyEditTBH',
    version='version_info.txt' if IS_WINDOWS else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX não é aplicado no macOS: comprimir o executável invalida a assinatura
    # de código e o Gatekeeper recusa abrir o resultado.
    upx=not IS_MACOS,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if IS_MACOS:
    app = BUNDLE(
        exe,
        name='HollyEditTBH.app',
        icon=None,
        bundle_identifier='com.hollygm.hollyedittbh',
        info_plist={
            'CFBundleDisplayName': 'HollyEditTBH',
            'CFBundleShortVersionString': '3.4.4',
            'CFBundleVersion': '3.4.4',
            'NSHighResolutionCapable': True,
        },
    )
