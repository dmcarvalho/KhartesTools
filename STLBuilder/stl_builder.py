import osgeo.gdal as gdal
import numpy as np
import os
import math

from raster import MDS
from stl_writer import StlWriter

from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtGui import QColor, QMessageBox, QProgressBar
from PyQt4.QtCore import Qt
from PyQt4.QtCore import pyqtSlot
from numbers import Real
# QGIS imports
from qgis.gui import QgsRubberBand
from qgis._core import QgsPoint, QgsGeometry, QgsCoordinateTransform, QgsRectangle
from qgis.core import QgsCoordinateReferenceSystem
from subprocess import call

FORM_CLASS, _ = uic.loadUiType(os.path.join(
os.path.dirname(__file__), 'stl_builder.ui'))


def calcNormal(p0, p1, p2):
    '''
    Calcula o vetor normal ao plano definido pelos pontos nao colineares
    p0, p1 e p2.
    '''
    v1 = p1 - p0
    v2 = p2 - p0
    return np.cross(v1, v2)



class STLBuilder(QtGui.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(STLBuilder, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        try:
            self.map_crs = self.canvas.mapSettings().destinationCrs()
        except:
            self.map_crs = self.canvas.mapRenderer().destinationCrs()
        output_folder_path = None
        self.message = None
        self.geometries_blocks = None 
        self.layers = {}   
        self.geo_blocks = []
        self.blocks = []
        self.setupUi(self) 
        
    def closeEvent(self, *args, **kwargs):
        self.erase_blocks()
        return QtGui.QDialog.closeEvent(self, *args, **kwargs)
    
    def its_ok(self):
        its_ok = False
        self.layers = {}
        for layer in self.canvas.layers():
            if layer.type() == 1:
                self.layers[layer.name()] = layer
                its_ok =  True
        if not its_ok:
            self.message = self.tr("No visible raster layer loaded")
        return its_ok
    
    def exec_(self, *args, **kwargs):
        for layer_name in self.layers.keys():
            self.layer_ComboBox.addItem(layer_name)
        self.paint_blocks()
        return QtGui.QDialog.exec_(self, *args, **kwargs)
    
    def finished(self, *args, **kwargs):
        self.erase_blocks()        
        return QtGui.QDialog.finished(self, *args, **kwargs)
    
    @pyqtSlot(int, name='on_x_spinBox_valueChanged')
    @pyqtSlot(int, name='on_y_spinBox_valueChanged')
    @pyqtSlot(int, name='on_z_spinBox_valueChanged')
    @pyqtSlot(int, name='on_h_scale_spinBox_valueChanged')
    def spinbox_int_value(self, i):
        self.paint_blocks()  

    @pyqtSlot(float, name='on_v_exaggeration_doubleSpinBox_valueChanged')
    def spinbox_double_value(self, i):
        self.paint_blocks()
        
    @pyqtSlot(int)
    def on_layer_ComboBox_activated(self, i):
        self.paint_blocks()  

    def validateParams(self):
        if self.x_spinBox.value() == 0:
            return (False, self.tr('Define X size model'))           
        if self.y_spinBox.value() == 0:
            return (False, self.tr('Define Y size model'))
        if self.z_spinBox.value() == 0:
            return (False, self.tr('Define Z size model'))
        if self.h_scale_spinBox.value() == 0:
            return (False, self.tr('Define Horizontal Scale'))                    
        if self.v_exaggeration_doubleSpinBox.value() == 0:
            return (False, self.tr('Define Vertical Exaggeration'))  
        
        self.size_block_x = self.x_spinBox.value()
        self.size_block_y = self.y_spinBox.value()
        self.size_block_z = self.x_spinBox.value()
        
        # dimensionless
        self.h_scale = 1.0 / self.h_scale_spinBox.value()

        layer_name = self.layer_ComboBox.currentText()
        self.layer = self.layers[layer_name]
 
        source_src = self.layer.crs()
        self.rec = self.layer.extent()          
           
        #uppreleft
        xmin = self.rec.xMinimum()
        ymax = self.rec.yMaximum()         
        #upertight
        xmax = self.rec.xMaximum()
        ymin = self.rec.yMinimum()
       
        width_general = self.calcBlockGeoSize(source_src, xmax-xmin, self.h_scale)
        height_general = self.calcBlockGeoSize(source_src, ymax-ymin, self.h_scale)
                
        width_geo = xmax - xmin
        height_geo = ymax - ymin

        self.step_x = width_geo/(width_general/self.size_block_x)
        self.step_y = height_geo/(height_general/self.size_block_y)
        
        self.num_blocks_x = int(width_general/self.size_block_x) + 1
        self.num_blocks_y = int(height_general/self.size_block_y) + 1
        
        if self.num_blocks_x * self.num_blocks_y > 1000:
            return (False, self.tr('This setting will produce many blocks. That seems wrong'))
        return (True, '')
    
    def calcBlockGeoSize(self, crs, distance, scale):
        if crs.mapUnits() == 0:  # Meters
            return distance*1000*scale
        elif crs.mapUnits() == 2:  # Degree
            return  distance * 1000 * scale * math.pi / 180 * 6371000
        
    def calculateBlocks(self):
        ok, msg = self.validateParams()
        if not ok:
            QMessageBox.warning(self, self.tr("Attention"), msg)
            return []

        #uppreleft
        xmin = self.rec.xMinimum()
        ymax = self.rec.yMaximum()         
        #upertight
        xmax = self.rec.xMaximum()
        ymin = self.rec.yMinimum()
              
        self.geo_blocks = []
        for i in range(self.num_blocks_x):
            x_min = xmin + i * self.step_x
            if i < self.num_blocks_x-1:
                x_max = x_min + self.step_x
            else:
                x_max = xmax
            for j in range(self.num_blocks_y):          
                y_max = ymax - j * self.step_y
                if j < self.num_blocks_y-1:
                    y_min = y_max - self.step_y
                else:
                    y_min = ymin
                self.geo_blocks.append(QgsRectangle(x_min, y_min, x_max, y_max))
        self.geo_blocks
         
    def paint_blocks(self):
        self.erase_blocks()
        self.blocks = []        
        
        layer_name = self.layer_ComboBox.currentText()
        layer = self.layers[layer_name]
        rec = layer.extent()
        
        source = layer.crs()
        target = self.map_crs
        transform = QgsCoordinateTransform(source, target)
        self.calculateBlocks()
        for rec in self.geo_blocks:
            rec = transform.transform(rec)
            self.blocks.append(self.paint_block(rec))

    
    def paint_block(self, rec, params= {'Color': QColor(255, 0, 0, 255), 'Width': 2, 'LineStyle': Qt.PenStyle(Qt.SolidLine)}):
        self.roi_x_max = rec.xMaximum()
        self.roi_y_min = rec.yMinimum()
        self.roi_x_min = rec.xMinimum()
        self.roi_y_max = rec.yMaximum()

        block = QgsRubberBand(self.canvas, True)
        points = [QgsPoint(self.roi_x_max, self.roi_y_min), QgsPoint(self.roi_x_max, self.roi_y_max),
                  QgsPoint(self.roi_x_min, self.roi_y_max), QgsPoint(self.roi_x_min, self.roi_y_min),
                  QgsPoint(self.roi_x_max, self.roi_y_min)]
        block.setToGeometry(QgsGeometry.fromPolyline(points), None)
        block.setColor(params['Color'])
        block.setWidth(params['Width'])
        block.setLineStyle(params['LineStyle'])
        self.canvas.refresh()
        return block
        
    def erase_blocks(self):
        if self.blocks:
            for block in self.blocks:
                self.erase_block(block)
        self.blocks = None

    def erase_block(self, block):
        self.canvas.scene().removeItem(block)
        
        
    @pyqtSlot(bool)
    def on_cancel_pushButton_clicked(self):
        '''
        Closes the dialog
        '''
        self.erase_blocks()
        self.done(0)
        
    @pyqtSlot()    
    def on_output_PushButton_clicked(self): 
        '''
        Defines destination folder
        '''
        fd = QtGui.QFileDialog()
        self.output_folder_path = fd.getExistingDirectory()
        if self.output_folder_path <> "":
            self.carregado = True
            self.output_folder_LineEdit.setText(self.output_folder_path)
    
    
    @pyqtSlot()    
    def on_builder_pushButton_clicked(self):
        ok, msg = self.validateParams()
        if not ok:
            QMessageBox.warning(self, self.tr("Attention"), msg)
            return
        output_path = self.output_folder_LineEdit.text()
        if not os.path.isdir(output_path):
            QMessageBox.warning(self, self.tr("Attention"), self.tr('You must choose a directory.'))
            return        # dimensionless
        h_scale = 1.0 / self.h_scale_spinBox.value()
        z_scale = h_scale * self.v_exaggeration_doubleSpinBox.value()
        
        layer_name = self.layer_ComboBox.currentText()
        layer = self.layers[layer_name]
        
        crs = layer.crs()
        layer_source = layer.source()

        
        for i in range(len(self.geo_blocks)):
            rec = self.geo_blocks[i]
            #uppreleft
            ul_x = rec.xMinimum()
            ul_y = rec.yMaximum()
            #upertight
            lr_x = rec.xMaximum()
            lr_y = rec.yMinimum() 
            block_name = os.path.join(output_path, '%s.tif' % (i))
            comando_dem = 'gdal_translate -projwin %s %s %s %s -of GTiff %s %s' % (ul_x, ul_y, lr_x, lr_y, os.path.join('',layer_source), block_name)
            call(comando_dem, shell=True)
            #self.block_files.append(block_name)

            s_raster = gdal.Open(block_name)
            band = s_raster.GetRasterBand(1)
            grid = band.ReadAsArray()
        
            z_min = np.min(grid)
        
            geotransform = s_raster.GetGeoTransform()
            s_origin_x = geotransform[0]  # decimal degree
            s_origin_y = geotransform[3]  # decimal degree
            s_pixel_width = geotransform[1]
            s_pixel_height = geotransform[5]
        
            s_colls = s_raster.RasterXSize
            s_rows = s_raster.RasterYSize
            z_min = np.min(grid)
            z_max = np.max(grid)
        
            ul = [ul_x, ul_y]
            lr = [lr_x, lr_y]
        
            x_extension = self.calcBlockGeoSize(crs, lr[0]-ul[0], h_scale)
            y_extension = self.calcBlockGeoSize(crs, ul[1]-lr[1], h_scale)
        
            params = {}
            params['s_colls'] = s_colls
            params['s_rows'] = s_rows
            params['s_origin_x'] = 0
            params['s_origin_y'] = y_extension
            params['s_pixel_width'] = x_extension / s_colls
            params['s_pixel_height'] = -y_extension / s_rows
            params['s_x_rotation'] = geotransform[2]
            params['s_y_rotation'] = geotransform[4]
        
            grid = (grid * 1000) * z_scale

            stl_file_name = os.path.join(output_path, '%s.stl' % os.path.basename(block_name)[:-4])
            stl_file = StlWriter(stl_file_name, False)
            stl_file.first_line_writer()
            faces = []
            for row in range(s_rows - 1):
                for column in range(s_colls - 1):
                    v0 = np.array([params['s_origin_x'] + params['s_pixel_width'] * column,
                                   params['s_origin_y'] +
                                   (params['s_pixel_height'] * row),
                                   grid[row][column]])
        
                    v1 = np.array([params['s_origin_x'] + params['s_pixel_width'] * (column + 1),
                                   params['s_origin_y'] +
                                   (params['s_pixel_height'] * row),
                                   grid[row][column + 1]])
        
                    v2 = np.array([params['s_origin_x'] + params['s_pixel_width'] * column,
                                   params['s_origin_y'] +
                                   (params['s_pixel_height'] * (row + 1)),
                                   grid[row + 1][column]])
        
                    normal = calcNormal(v0, v2, v1)
                    faces.append((v0, v2, v1, normal))
                    #stl_file.facet_writer()
        
                    # Calculate the second facet (just the one new point)
                    v3 = np.array([params['s_origin_x'] + params['s_pixel_width'] * (column + 1),
                                   params['s_origin_y'] +
                                   (params['s_pixel_height'] * (row + 1)),
                                   grid[row + 1][column + 1]])
                    normal = calcNormal(v2, v3, v1)
                    faces.append((v2, v3, v1, normal))
            for v0, v1, v2, normal in faces:
                stl_file.facet_writer(v0, v1, v2, normal)
            stl_file.end_line_writer()
            stl_file = None
        
        QMessageBox.warning(self, self.tr("Attention"), self.tr('Successfully built files'))
        self.erase_blocks()
        self.done(0)