# Retro Skin - QGIS plugin
# Copyright (C) 2026 Vertical S.r.l.
# SPDX-License-Identifier: GPL-2.0-or-later

def classFactory(iface):
    from .retro_skin import RetroSkin
    return RetroSkin(iface)
