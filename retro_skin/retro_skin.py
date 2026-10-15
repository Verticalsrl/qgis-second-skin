# Copyright (C) 2026 Vertical S.r.l.
# SPDX-License-Identifier: GPL-2.0-or-later
"""Retro Skin: switch the QGIS look (stylesheet and icons) on the fly.

Each skin is a folder skins/<id>/ containing:
  skin.json   name, stylesheet, icon size, map icon -> objectName of QGIS actions
  style.qss   Qt stylesheet
  toolbars    (optional) toolbars rebuilt from QGIS actions, in the original software order
  menus/docks (optional) alternative titles for menus and panels, by objectName
  icons/      PNG <name>.png (16px) and <name>@2x.png (32px, for HiDPI screens)
To add a skin just copy a folder and edit it.
Texts are in English, with Italian used when the QGIS locale is Italian.
"""
import json
import os

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QLocale, QSize, Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (QApplication, QDockWidget, QMenu, QToolBar,
                                 QToolButton)

try:  # Qt5 (QGIS 3)
    from qgis.PyQt.QtWidgets import QAction, QActionGroup
except ImportError:  # Qt6 (QGIS 4)
    from qgis.PyQt.QtGui import QAction, QActionGroup

PLUGIN_DIR = os.path.dirname(__file__)
SKINS_DIR = os.path.join(PLUGIN_DIR, 'skins')
DEFAULT_ID = 'default'
SETTINGS_KEY = 'retro_skin/current'
HIDDEN_KEY = 'retro_skin/hidden_toolbars'   # only used by 0.4, which hid the QGIS toolbars
LANG_KEY = 'retro_skin/language'            # 'auto' (follow QGIS), 'en' or 'it'

TEXTS = {
    'en': {
        'original': 'QGIS (original)',
        'original_desc': 'Restore the standard look',
        'next': 'Next skin  (Ctrl+Alt+K)',
        'rescue': 'Restore QGIS toolbars',
        'create': 'Create your own skin (open skins folder)',
        'change': 'Change skin',
        'about': ("Retro Skin: just for fun, a toy for GIS nostalgics.\n"
                  "Anyone can freely create their own skins: "
                  "copy a folder in skins/ and edit it."),
        'share': 'Share your skin / create one with AI  (coming soon)',
        'share_tip': ('Coming soon: ready-made AI prompts to generate a skin, '
                      'and a page to upload and share it with everyone.'),
        'active': 'Active skin: {}',
        'restored': 'Restored {} QGIS toolbars',
        'language': 'Language',
        'lang_auto': 'Same as QGIS',
    },
    'it': {
        'original': 'QGIS (originale)',
        'original_desc': "Ripristina l'aspetto standard",
        'next': 'Skin successiva  (Ctrl+Alt+K)',
        'rescue': 'Ripristina toolbar QGIS',
        'create': 'Crea la tua skin (apri cartella skin)',
        'change': 'Cambia skin',
        'about': ("Retro Skin: un gioco per i nostalgici del GIS.\n"
                  "Ognuno puo' creare liberamente le proprie skin: "
                  "copia una cartella in skins/ e modificala."),
        'share': 'Condividi la tua skin / creala con l\'AI  (in arrivo)',
        'share_tip': ('In arrivo: prompt pronti per generare una skin con l\'AI '
                      'e una pagina per caricarla e condividerla con tutti.'),
        'active': 'Skin attiva: {}',
        'restored': 'Ripristinate {} toolbar QGIS',
        'language': 'Lingua',
        'lang_auto': 'Come QGIS',
    },
}


LANGUAGES = [('en', 'English'), ('it', 'Italiano')]


def _language():
    chosen = QgsSettings().value(LANG_KEY, 'auto')
    if chosen in TEXTS:
        return chosen
    locale = QgsSettings().value('locale/userLocale', '') or QLocale().name()
    lang = str(locale)[:2].lower()
    return lang if lang in TEXTS else 'en'


def tr(key):
    return TEXTS[_language()].get(key, TEXTS['en'][key])


def localized(data, key):
    """Return data['<key>_<lang>'] if present (e.g. description_it), else data[key]."""
    return data.get(f'{key}_{_language()}') or data.get(key, '')


class RetroSkin:
    def __init__(self, iface):
        self.iface = iface
        self.skins = {}
        self.current = DEFAULT_ID
        # original state, saved only once so it can be restored
        self._orig_stylesheet = None
        self._orig_icons = {}         # QAction -> QIcon
        self._orig_icon_sizes = {}    # QToolBar -> QSize
        self._orig_titles = []        # (widget, original text)
        self._skin_toolbars = []      # toolbars created by the skin
        self.menu = None
        self.toolbar = None
        self.button = None
        self.group = None
        self._cycle_action = None

    # ---------------------------------------------------------------- setup
    def initGui(self):
        self._load_skins()
        icon = QIcon(os.path.join(PLUGIN_DIR, 'icons', 'retroskin.png'))
        icon.addFile(os.path.join(PLUGIN_DIR, 'icons', 'retroskin@2x.png'), QSize(32, 32))

        self.menu = QMenu('Retro Skin')
        self.menu.setIcon(icon)
        self.menu.setToolTipsVisible(True)
        self.iface.pluginMenu().addMenu(self.menu)

        self.toolbar = self.iface.addToolBar('Retro Skin')
        self.toolbar.setObjectName('RetroSkinToolbar')
        self.button = QToolButton()
        self.button.setIcon(icon)
        self.button.setMenu(self.menu)
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(self.button)

        self._build_menu()

        saved = QgsSettings().value(SETTINGS_KEY, DEFAULT_ID)
        self._check(DEFAULT_ID)
        # 0.4 hid the QGIS toolbars: show them again once and for all
        if QgsSettings().value(HIDDEN_KEY):
            QTimer.singleShot(0, self.show_qgis_toolbars)
        if saved != DEFAULT_ID and saved in self.skins:
            # wait until QGIS has created all its toolbars
            QTimer.singleShot(0, lambda: self.apply(saved))

    def _build_menu(self):
        """(Re)create the menu entries in the current language."""
        if self._cycle_action is not None:
            self.iface.unregisterMainWindowAction(self._cycle_action)
        self.menu.clear()
        if self.group is not None:
            self.group.deleteLater()
        self.skins[DEFAULT_ID].update(name=tr('original'), description=tr('original_desc'))
        self.button.setToolTip(tr('change') + '\n\n' + tr('about'))

        self.group = QActionGroup(self.menu)
        self.group.setExclusive(True)
        for skin_id, skin in self._ordered_skins():
            act = QAction(localized(skin, 'name'), self.menu)
            act.setCheckable(True)
            act.setData(skin_id)
            act.setToolTip(localized(skin, 'description'))
            act.triggered.connect(lambda _=False, s=skin_id: self.apply(s))
            self.group.addAction(act)
            self.menu.addAction(act)
        self.menu.addSeparator()
        cycle = QAction(tr('next'), self.menu)
        cycle.triggered.connect(self.cycle)
        self.menu.addAction(cycle)
        rescue = QAction(tr('rescue'), self.menu)
        rescue.triggered.connect(self.show_qgis_toolbars)
        self.menu.addAction(rescue)
        self.menu.addSeparator()
        folder = QAction(tr('create'), self.menu)
        folder.setToolTip(tr('about'))
        folder.triggered.connect(self.open_skins_folder)
        self.menu.addAction(folder)
        share_icon = QIcon(os.path.join(PLUGIN_DIR, 'icons', 'share.png'))
        share_icon.addFile(os.path.join(PLUGIN_DIR, 'icons', 'share@2x.png'), QSize(32, 32))
        share = QAction(share_icon, tr('share'), self.menu)
        share.setToolTip(tr('share_tip'))
        share.triggered.connect(
            lambda: self.iface.messageBar().pushInfo('Retro Skin', tr('share_tip')))
        self.menu.addAction(share)

        self.menu.addSeparator()
        lang_menu = self.menu.addMenu(tr('language') + ' / Language')
        lang_group = QActionGroup(lang_menu)
        chosen = QgsSettings().value(LANG_KEY, 'auto')
        for code, label in [('auto', tr('lang_auto'))] + LANGUAGES:
            act = QAction(label, lang_menu)
            act.setCheckable(True)
            act.setChecked(code == chosen)
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
            lang_group.addAction(act)
            lang_menu.addAction(act)

        self.iface.registerMainWindowAction(cycle, 'Ctrl+Alt+K')
        self._cycle_action = cycle
        self._check(self.current)

    def set_language(self, code):
        QgsSettings().setValue(LANG_KEY, code)
        self._build_menu()

    def unload(self):
        self.apply(DEFAULT_ID, save=False)
        self.iface.unregisterMainWindowAction(self._cycle_action)
        self.iface.pluginMenu().removeAction(self.menu.menuAction())
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
        self.menu.deleteLater()

    def open_skins_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(SKINS_DIR))

    # ----------------------------------------------------------------- skin
    def _load_skins(self):
        self.skins = {DEFAULT_ID: {'name': tr('original'),
                                   'description': tr('original_desc')}}
        if not os.path.isdir(SKINS_DIR):
            return
        for skin_id in sorted(os.listdir(SKINS_DIR)):
            path = os.path.join(SKINS_DIR, skin_id, 'skin.json')
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                self.iface.messageBar().pushWarning('Retro Skin', f'{skin_id}: {e}')
                continue
            data['dir'] = os.path.join(SKINS_DIR, skin_id)
            self.skins[skin_id] = data

    def _ordered_skins(self):
        yield DEFAULT_ID, self.skins[DEFAULT_ID]
        for k, v in self.skins.items():
            if k != DEFAULT_ID:
                yield k, v

    def _check(self, skin_id):
        for act in self.group.actions():
            act.setChecked(act.data() == skin_id)

    def cycle(self):
        ids = [k for k, _ in self._ordered_skins()]
        nxt = ids[(ids.index(self.current) + 1) % len(ids)] if self.current in ids else DEFAULT_ID
        self.apply(nxt)

    def apply(self, skin_id, save=True):
        app = QApplication.instance()
        main = self.iface.mainWindow()
        if self._orig_stylesheet is None:
            self._orig_stylesheet = app.styleSheet()

        self._restore_original(main)
        if skin_id == DEFAULT_ID or skin_id not in self.skins:
            app.setStyleSheet(self._orig_stylesheet)
            self.current = DEFAULT_ID
        else:
            skin = self.skins[skin_id]
            qss = ''
            if skin.get('stylesheet'):
                with open(os.path.join(skin['dir'], skin['stylesheet']), encoding='utf-8') as f:
                    qss = f.read().replace('@SKINS_DIR@', SKINS_DIR.replace('\\', '/'))
            app.setStyleSheet(self._orig_stylesheet + '\n' + qss)
            self._apply_icons(main, skin)
            self._apply_titles(main, skin)
            self._apply_toolbars(main, skin)
            size = skin.get('toolbar_icon_size')
            if size:
                for tb in main.findChildren(QToolBar):
                    self._orig_icon_sizes.setdefault(tb, tb.iconSize())
                    tb.setIconSize(QSize(size, size))
            self.current = skin_id

        self._check(self.current)
        if save:
            QgsSettings().setValue(SETTINGS_KEY, self.current)
            name = localized(self.skins.get(self.current, {}), 'name') or self.current
            self.iface.messageBar().pushInfo('Retro Skin', tr('active').format(name))

    def _apply_icons(self, main, skin):
        by_name = {}
        for act in main.findChildren(QAction):
            if act.objectName():
                by_name.setdefault(act.objectName(), []).append(act)
        icons_dir = os.path.join(skin['dir'], 'icons')
        for icon_name, object_names in skin.get('icons', {}).items():
            base = os.path.join(icons_dir, icon_name + '.png')
            if not os.path.isfile(base):
                continue
            icon = QIcon(base)
            hidpi = os.path.join(icons_dir, icon_name + '@2x.png')
            if os.path.isfile(hidpi):
                icon.addFile(hidpi, QSize(32, 32))
            for obj in object_names:
                for act in by_name.get(obj, []):
                    self._orig_icons.setdefault(act, act.icon())
                    act.setIcon(icon)

    def _apply_titles(self, main, skin):
        for obj, text in skin.get('menus', {}).items():
            menu = main.findChild(QMenu, obj)
            if menu is not None:
                self._orig_titles.append((menu, menu.title()))
                menu.setTitle(text)
        for obj, text in skin.get('docks', {}).items():
            dock = main.findChild(QDockWidget, obj)
            if dock is not None:
                self._orig_titles.append((dock, dock.windowTitle()))
                dock.setWindowTitle(text)

    def _actions_by_name(self, main):
        by_name = {}
        for act in main.findChildren(QAction):
            if act.objectName():
                by_name.setdefault(act.objectName(), act)
        return by_name

    def show_qgis_toolbars(self):
        """Show again the toolbars hidden by version 0.4."""
        main = self.iface.mainWindow()
        settings = QgsSettings()
        hidden = settings.value(HIDDEN_KEY, []) or []
        if isinstance(hidden, str):
            hidden = [hidden]
        shown = 0
        for name in hidden:
            tb = main.findChild(QToolBar, name)
            if tb is not None and not tb.isVisible():
                tb.show()
                shown += 1
        settings.remove(HIDDEN_KEY)
        if shown:
            self.iface.messageBar().pushInfo('Retro Skin', tr('restored').format(shown))

    def _apply_toolbars(self, main, skin):
        """Add the original-software-style toolbars at the top.
        All QGIS toolbars stay visible below them."""
        bars = skin.get('toolbars')
        if not bars:
            return
        by_name = self._actions_by_name(main)
        top = [tb for tb in main.findChildren(QToolBar)
               if tb.parent() is main and tb.isVisible()
               and main.toolBarArea(tb) == Qt.ToolBarArea.TopToolBarArea]
        top.sort(key=lambda tb: (tb.y(), tb.x()))
        first = top[0] if top else None
        size = skin.get('toolbar_icon_size', 16)
        for spec in bars:
            tb = QToolBar(spec['name'], main)
            tb.setObjectName('RetroSkin_' + spec['name'].replace(' ', '_'))
            tb.setIconSize(QSize(size, size))
            for obj in spec.get('actions', []):
                if obj == '|':
                    tb.addSeparator()
                elif obj in by_name:
                    tb.addAction(by_name[obj])
            if first is not None:
                main.insertToolBar(first, tb)
                main.insertToolBarBreak(first)
            else:
                main.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
            tb.show()
            self._skin_toolbars.append(tb)

    def _restore_toolbars(self, main):
        for tb in self._skin_toolbars:
            try:
                main.removeToolBar(tb)
                tb.deleteLater()
            except RuntimeError:
                pass
        self._skin_toolbars.clear()

    def _restore_original(self, main):
        self._restore_toolbars(main)
        for widget, text in reversed(self._orig_titles):
            try:
                if isinstance(widget, QMenu):
                    widget.setTitle(text)
                else:
                    widget.setWindowTitle(text)
            except RuntimeError:
                pass
        self._orig_titles.clear()
        for act, icon in self._orig_icons.items():
            try:
                act.setIcon(icon)
            except RuntimeError:   # action already destroyed
                pass
        self._orig_icons.clear()
        for tb, size in self._orig_icon_sizes.items():
            try:
                tb.setIconSize(size)
            except RuntimeError:
                pass
        self._orig_icon_sizes.clear()
