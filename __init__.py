# -*- coding: utf-8 -*-
"""
/***************************************************************************
 KhartesTools
                                 A QGIS plugin
 This plugin gathers the tools developed by the company Khartes
                             -------------------
        begin                : 2016-09-11
        copyright            : (C) 2016 by Diego Moreira / Khartes Geoinformação
        email                : diego@khartes.com.br
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load KhartesTools class from file KhartesTools.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .khartes_tolls import KhartesTools
    return KhartesTools(iface)
