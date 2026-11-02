# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

added_files = [
    ('phonetransfer/assets', 'phonetransfer/assets'),
    ('bin', 'bin'),
    ('AppIcon.icns', '.'),
]

a = Analysis(
    ['phone_transfer.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PhoneTransfer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='AppIcon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='PhoneTransfer',
)

app = BUNDLE(
    coll,
    name='PhoneTransfer.app',
    icon='AppIcon.icns',
    bundle_identifier='local.phonetransfer.app',
    info_plist={
        'CFBundleName': 'PhoneTransfer',
        'CFBundleDisplayName': 'Phone Transfer',
        'CFBundleExecutable': 'PhoneTransfer',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',
        'CFBundleIdentifier': 'local.phonetransfer.app',
        'CFBundleVersion': '1.0.1',
        'CFBundleShortVersionString': '1.0.1',
        'NSHumanReadableCopyright': 'Copyright © 2026 qfxydx. All rights reserved.',
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'LSMinimumSystemVersion': '11.0',
    },
)

