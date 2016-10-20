import osgeo.gdal as gdal
import numpy as np
import os
import math

from stl_writer import StlWriter

from PyQt4 import QtGui, uic
from PyQt4.QtGui import QColor, QMessageBox, QProgressBar
from PyQt4.QtCore import Qt
from PyQt4.QtCore import pyqtSlot
# QGIS imports
from qgis.gui import QgsRubberBand
from qgis._core import QgsPoint, QgsGeometry, QgsCoordinateTransform, QgsRectangle
from qgis.core import QgsCoordinateReferenceSystem

m2mm = 1000.

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
        self.screen_blocks = []
        self.setupUi(self) 
        
    def closeEvent(self, *args, **kwargs):
        self.erase_blocks()
        return QtGui.QDialog.closeEvent(self, *args, **kwargs)

    def finished(self, *args, **kwargs):
        self.erase_blocks()        
        return QtGui.QDialog.finished(self, *args, **kwargs)
       
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
        self.size_block_z = self.z_spinBox.value()
        
        # dimensionless
        self.h_scale = 1.0 / self.h_scale_spinBox.value()
        self.z_scale = self.h_scale * self.v_exaggeration_doubleSpinBox.value()
        
        self.layer_name = self.layer_ComboBox.currentText()
        self.layer = self.layers[self.layer_name]
 
        self.layer_source = self.layer.source()
        self.layer_crs = self.layer.crs()
        self.layer_rec = self.layer.extent()          
           
        #uppreleft
        xmin = self.layer_rec.xMinimum()
        ymax = self.layer_rec.yMaximum()         
        #upertight
        xmax = self.layer_rec.xMaximum()
        ymin = self.layer_rec.yMinimum()
       
        width_general = self.calcBlockGeoSize(self.layer_crs, xmax-xmin, self.h_scale)
        height_general = self.calcBlockGeoSize(self.layer_crs, ymax-ymin, self.h_scale)
                
        width_geo = xmax - xmin
        height_geo = ymax - ymin

        self.step_x = width_geo/(width_general/self.size_block_x)
        self.step_y = height_geo/(height_general/self.size_block_y)
        
        self.num_blocks_x = int(width_general/self.size_block_x) + 1
        self.num_blocks_y = int(height_general/self.size_block_y) + 1
        
        if self.num_blocks_x * self.num_blocks_y > 1000:
            return (False, self.tr('This setting will produce many blocks. That seems wrong'))
        
        s_raster = gdal.Open(self.layer_source)
        band = s_raster.GetRasterBand(1)
        grid = band.ReadAsArray()
        
        self.z_min = np.min(grid)
        self.z_max = np.max(grid)
        if (self.z_max-self.z_min)*m2mm*self.z_scale >= self.size_block_z:
            v_exaggeration = round((self.size_block_z/((self.z_max-self.z_min)*m2mm))/self.h_scale, 2)
            self.v_exaggeration_doubleSpinBox.setValue(v_exaggeration - 0.01)
            return (False, self.tr('Vertical Exaggeration is very large. Select a value less than %s' % (v_exaggeration)))
        s_raster = None
            
        return (True, '')
    
    def calcBlockGeoSize(self, crs, distance, scale):
        if crs.mapUnits() == 0:  # Meters
            return distance*m2mm*scale
        elif crs.mapUnits() == 2:  # Degree
            return  distance * m2mm * scale * math.pi / 180 * 6371000
        
    def calculateBlocks(self):
        #uppreleft
        xmin = self.layer_rec.xMinimum()
        ymax = self.layer_rec.yMaximum()         
        #upertight
        xmax = self.layer_rec.xMaximum()
        ymin = self.layer_rec.yMinimum()
              
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
        self.screen_blocks = [] 
        ok, msg = self.validateParams()
        if not ok:
            QMessageBox.warning(self, self.tr("Attention"), msg)
            return []

        self.calculateBlocks()
        
        transform = QgsCoordinateTransform(self.layer_crs, self.map_crs)
        for rec in self.geo_blocks:
            rec = transform.transform(rec)
            self.screen_blocks.append(self.paint_block(rec))

    
    def paint_block(self, rec):
        self.roi_x_max = rec.xMaximum()
        self.roi_y_min = rec.yMinimum()
        self.roi_x_min = rec.xMinimum()
        self.roi_y_max = rec.yMaximum()

        block = QgsRubberBand(self.canvas, True)
        points = [QgsPoint(self.roi_x_max, self.roi_y_min), QgsPoint(self.roi_x_max, self.roi_y_max),
                  QgsPoint(self.roi_x_min, self.roi_y_max), QgsPoint(self.roi_x_min, self.roi_y_min),
                  QgsPoint(self.roi_x_max, self.roi_y_min)]
        block.setToGeometry(QgsGeometry.fromPolyline(points), None)
        block.setColor(QColor(255, 0, 0, 255))
        block.setWidth(2)
        block.setLineStyle(Qt.PenStyle(Qt.SolidLine))
        self.canvas.refresh()
        return block
        
    def erase_blocks(self):
        if self.screen_blocks:
            for block in self.screen_blocks:
                self.erase_block(block)
        self.screen_blocks = None

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
            return        
        self.progressBar.setRange(0, len(self.geo_blocks))
        
        s_raster = gdal.Open(self.layer_source)
        band = s_raster.GetRasterBand(1)
        #grid_base = band.ReadAsArray()
        geotransform = s_raster.GetGeoTransform()
        
        s_pixel_width = geotransform[1]
        s_pixel_height = geotransform[5]
    
        
        for i in range(len(self.geo_blocks)):
            rec = self.geo_blocks[i]
            #uppreleft
            ul_x = rec.xMinimum()
            ul_x_pixel = int((ul_x - geotransform[0]) / geotransform[1]) 
            ul_y = rec.yMaximum()
            ul_y_pixel = int((ul_y - geotransform[3]) / geotransform[5]) 
            #upertight
            lr_x = rec.xMaximum()
            lr_x_pixel = int((lr_x - geotransform[0]) / geotransform[1]) 
            lr_y = rec.yMinimum() 
            lr_y_pixel = int((lr_y - geotransform[3]) / geotransform[5])

            s_colls = lr_x_pixel-ul_x_pixel
            s_rows = lr_y_pixel-ul_y_pixel

            x_extension = self.calcBlockGeoSize(self.layer_crs, lr_x-ul_x, self.h_scale)
            y_extension = self.calcBlockGeoSize(self.layer_crs, ul_y-lr_y, self.h_scale)
            
            s_origin_x = 0
            s_origin_y = y_extension
            s_pixel_width = x_extension / s_colls
            s_pixel_height = -y_extension / s_rows
            
            grid = band.ReadAsArray(ul_x_pixel, ul_y_pixel, s_colls, s_rows)
            
            grid = grid  * m2mm * self.z_scale  
            
            stl_file_name = os.path.join(output_path, '%s.stl' % i)
            stl_file = StlWriter(stl_file_name, False)
            stl_file.first_line_writer()
            facets = []
            #calculate facets of the surface
            for row in range(s_rows-1):
                for column in range(s_colls-1):
                    v0 = np.array([s_origin_x + s_pixel_width * column, s_origin_y + (s_pixel_height * row), grid[row][column]])
                    v1 = np.array([s_origin_x + s_pixel_width * (column + 1),s_origin_y + (s_pixel_height * row), grid[row][column + 1]])
                    v2 = np.array([s_origin_x + s_pixel_width * column, s_origin_y + (s_pixel_height * (row + 1)), grid[row + 1][column]])
                    normal = calcNormal(v0, v2, v1)
                    facets.append((v0, v2, v1, normal))
                    
                    v3 = np.array([s_origin_x + s_pixel_width * (column + 1), s_origin_y + (s_pixel_height * (row + 1)), grid[row + 1][column + 1]])
                    normal = calcNormal(v2, v3, v1)
                    facets.append((v2, v3, v1, normal))
            stl_file.facet_writer(facets)
            
            #calculate the wall
            base = self.z_min  * m2mm * self.z_scale
            height = s_origin_y + (s_pixel_height * s_rows)
            facets = []
            for column in range(s_colls - 1):
                v0 = np.array([s_origin_x + s_pixel_width * column, s_origin_y, grid[0][column]])
                v1 = np.array([s_origin_x + s_pixel_width * (column + 1), s_origin_y , grid[0][column + 1]])
                v2 = np.array([s_origin_x + s_pixel_width * (column + 1), s_origin_y, base])
                normal = calcNormal(v2,v0, v1)
                facets.append(( v2, v0, v1, normal))
                
                v3 = np.array([s_origin_x + s_pixel_width * column, s_origin_y , grid[0][column]])
                v4 = np.array([s_origin_x + s_pixel_width * column, s_origin_y , base])
                v5 = np.array([s_origin_x + s_pixel_width * (column + 1), s_origin_y, base])
                normal = calcNormal(v3, v5, v4)
                facets.append((v3, v5, v4, normal))
                
                # another wal
                v0 = np.array([s_origin_x + s_pixel_width * column, height, grid[s_rows-1][column]])
                v1 = np.array([s_origin_x + s_pixel_width * (column + 1), height , grid[s_rows-1][column + 1]])
                v2 = np.array([s_origin_x + s_pixel_width * (column + 1), height, base])
                normal = calcNormal(v0, v2, v1)
                facets.append(( v0, v2, v1, normal))
                
                v3 = np.array([s_origin_x + s_pixel_width * column, height , grid[s_rows-1][column]])
                v4 = np.array([s_origin_x + s_pixel_width * column, height , base])
                v5 = np.array([s_origin_x + s_pixel_width * (column + 1), height, base])
                normal = calcNormal(v5, v3, v4)
                facets.append((v5, v3, v4, normal))
            stl_file.facet_writer(facets)

            width = s_origin_x + s_pixel_width * s_colls
            facets = []
            for row in range(s_rows - 1):
                v0 = np.array([s_origin_x, s_origin_y + s_pixel_height * row, grid[row][0]])
                v1 = np.array([s_origin_x, s_origin_y + s_pixel_height * (row+1) , grid[row+1][0]])
                v2 = np.array([s_origin_x, s_origin_y + s_pixel_height * (row+1), base])
                normal = calcNormal(v0, v2, v1)
                facets.append((v0, v2, v1, normal))
                
                v3 = np.array([s_origin_x, s_origin_y + s_pixel_height * row, grid[row][0]] )
                v4 = np.array([s_origin_x, s_origin_y + s_pixel_height * (row+1), base])
                v5 = np.array([s_origin_x, s_origin_y + s_pixel_height * row, base])
                normal = calcNormal(v3, v5, v4)
                facets.append((v3, v5, v4, normal))
                
                v0 = np.array([width, s_origin_y + s_pixel_height * row, grid[row][s_colls-1]])
                v1 = np.array([width, s_origin_y + s_pixel_height * (row+1) , grid[row+1][s_colls-1]])
                v2 = np.array([width, s_origin_y + s_pixel_height * (row+1), base])
                normal = calcNormal(v2, v0, v1)
                facets.append((v2, v0, v1, normal))
                
                v3 = np.array([width, s_origin_y + s_pixel_height * row, grid[row][s_colls-1]] )
                v4 = np.array([width, s_origin_y + s_pixel_height * (row+1), base])
                v5 = np.array([width, s_origin_y + s_pixel_height * row, base])
                normal = calcNormal(v5, v3, v4)
                facets.append((v5, v3, v4, normal))
                  
            stl_file.facet_writer(facets)
            
            
            stl_file.end_line_writer()
            stl_file = None
            self.progressBar.setValue(i+1)
        
        QMessageBox.warning(self, self.tr("Attention"), self.tr('Files built successfully'))
        self.erase_blocks()
        self.done(0)