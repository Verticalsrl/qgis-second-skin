#!/usr/bin/env python3
"""Build and check the zip to upload to https://plugins.qgis.org.

Usage: python3 scripts/package.py
Output: dist/retro_skin-<version>.zip

The checks mirror the ones run by the QGIS plugin repository on upload:
mandatory metadata, LICENSE inside the package, a single top-level folder
that is a valid Python package name, no compiled/hidden files, valid icon.
"""
import configparser
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = 'retro_skin'
SRC = os.path.join(ROOT, PLUGIN)
DIST = os.path.join(ROOT, 'dist')

REQUIRED = ['name', 'qgisMinimumVersion', 'description', 'about', 'version',
            'author', 'email', 'repository', 'tracker']
EXCLUDED_DIRS = {'__pycache__', '.git', '.idea', '.vscode', '__MACOSX'}
EXCLUDED_EXT = {'.pyc', '.pyo', '.orig', '.rej', '.bak', '.zip'}


def fail(msg):
    print('ERROR: ' + msg)
    sys.exit(1)


def read_metadata():
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    with open(os.path.join(SRC, 'metadata.txt'), encoding='utf-8') as f:
        cfg.read_file(f)
    meta = dict(cfg['general'])
    for key in REQUIRED:
        if not meta.get(key, '').strip():
            fail(f'metadata.txt: missing mandatory key "{key}"')
    for key in ('repository', 'tracker', 'homepage'):
        if key in meta and not re.match(r'^https?://', meta[key]):
            fail(f'metadata.txt: "{key}" must be a http(s) URL')
    if not re.match(r'^\d+\.\d+(\.\d+)?$', meta['version']):
        fail('metadata.txt: version must look like 1.2 or 1.2.3')
    if 'plugin' in meta['name'].lower():
        fail('metadata.txt: the name should not contain the word "plugin"')
    icon = os.path.join(SRC, meta.get('icon', ''))
    if not meta.get('icon') or not os.path.isfile(icon):
        fail('metadata.txt: icon not found')
    return meta


def collect_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in EXCLUDED_DIRS and not d.startswith('.'))
        for name in sorted(filenames):
            if name.startswith('.') or os.path.splitext(name)[1] in EXCLUDED_EXT:
                continue
            files.append(os.path.join(dirpath, name))
    return files


def check_skins():
    skins = os.path.join(SRC, 'skins')
    for skin_id in sorted(os.listdir(skins)):
        path = os.path.join(skins, skin_id, 'skin.json')
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not data.get('name'):
            fail(f'{skin_id}/skin.json: missing "name"')
        qss = data.get('stylesheet')
        if qss and not os.path.isfile(os.path.join(skins, skin_id, qss)):
            fail(f'{skin_id}: stylesheet {qss} not found')
        for icon in data.get('icons', {}):
            if not os.path.isfile(os.path.join(skins, skin_id, 'icons', icon + '.png')):
                fail(f'{skin_id}: icon {icon}.png not found')


def main():
    meta = read_metadata()
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', PLUGIN):
        fail('plugin folder must be a valid Python package name')
    for name in ('__init__.py', 'metadata.txt', 'LICENSE'):
        if not os.path.isfile(os.path.join(SRC, name)):
            fail(f'{name} missing from {PLUGIN}/')
    check_skins()

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f'{PLUGIN}-{meta["version"]}.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in collect_files():
            z.write(path, os.path.relpath(path, ROOT))
    size = os.path.getsize(out) / 1024
    print(f'OK: {out} ({size:.0f} KB)')


if __name__ == '__main__':
    main()
