import osgeo.gdal as gdal
import numpy as np
import os

from geometry import pixel2Coord, calcBlockSize, calcNormal
from raster import MDS
from stl_writer import StlWriter

from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtGui import QColor
from PyQt4.QtCore import Qt
from PyQt4.QtCore import pyqtSlot
from numbers import Real
# QGIS imports
from qgis.gui import QgsRubberBand
from qgis._core import QgsPoint, QgsGeometry, QgsCoordinateTransform, QgsRectangle
from qgis.core import QgsCoordinateReferenceSystem

FORM_CLASS, _ = uic.loadUiType(os.path.join(
os.path.dirname(__file__), 'stl_builder.ui'))



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
        self.layer_extent = None   
        self.blocks = []
        self.setupUi(self) 
    def closeEvent(self, *args, **kwargs):
        print 'afasdgasdfg'
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

    def calculateBlocks(self):
        size_block_x = self.x_spinBox.value()
        size_block_y = self.y_spinBox.value()
        size_block_z = self.x_spinBox.value()
        # dimensionless
        h_scale = 1.0 / self.h_scale_spinBox.value()

        layer_name = self.layer_ComboBox.currentText()
        layer = self.layers[layer_name]
 
       
        source = layer.crs()
        wgs84_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        transform = QgsCoordinateTransform(source, wgs84_crs)
        
        rec = layer.extent()          
        rec = transform.transform(rec)  
           
        #uppreleft
        xmin = rec.xMinimum()
        ymax = rec.yMaximum()         
        #upertight
        xmax = rec.xMaximum()
        ymin = rec.yMinimum()
        
        width_general = calcBlockSize(xmin, xmax, h_scale, size_block_x, 1000)
        height_general = calcBlockSize(ymin, ymax, h_scale, size_block_y, 1000)
                
        width_wgs_84 = xmax - xmin
        height_wgs_84 = ymax - ymin

        step_x = width_wgs_84/(width_general/size_block_x)
        step_y = height_wgs_84/(height_general/size_block_y)
        
        num_blocks_x = int(width_general/size_block_x) + 1
        num_blocks_y = int(height_general/size_block_y) + 1

        transform = QgsCoordinateTransform(wgs84_crs, source)
        blocks = []
        for i in range(num_blocks_x):
            x_min = xmin + i * step_x
            if i < num_blocks_x-1:
                x_max = x_min + step_x
            else:
                x_max = xmax
            for j in range(num_blocks_y):          
                y_max = ymax - j * step_y
                if j < num_blocks_y-1:
                    y_min = y_max - step_y
                else:
                    y_min = ymin
                rec = transform.transform(QgsRectangle(x_min, y_min, x_max, y_max))
                blocks.append(rec)
        return blocks
         
    def paint_blocks(self):
        self.erase_blocks()
        self.blocks = []        
        
        layer_name = self.layer_ComboBox.currentText()
        layer = self.layers[layer_name]
        rec = layer.extent()
        
        source = layer.crs()
        print type(source)
        target = self.map_crs
        transform = QgsCoordinateTransform(source, target)
        rec = transform.transform(rec)            
        self.layer_extent = self.paint_block(rec, {'Color': QColor(0, 0, 255, 255), 'Width': 5, 'LineStyle': Qt.PenStyle(Qt.SolidLine)})        
        
        for rec in self.calculateBlocks():
            rec = transform.transform(rec)
            self.blocks.append(self.paint_block(rec))

    
    def paint_block(self, rec, params= {'Color': QColor(227, 26, 28, 255), 'Width': 2, 'LineStyle': Qt.PenStyle(Qt.DashDotLine)}):
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
        if self.layer_extent:
            self.erase_block(self.layer_extent)          
        self.blocks = None
        self.layer_extent = None

    def erase_block(self, block):
        self.canvas.scene().removeItem(block)
        
        
    @pyqtSlot(bool)
    def on_cancel_pushButton_clicked(self):
        '''
        Closes the dialog
        '''
        print 'entrou'
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
        noDataValue = -9999
        m2mm = 1000.0
        filePath = '/media/diego/SAMSUNG/srtm2stl/geo/raster/df_go.tif'
        outPutPath = '/media/diego/SAMSUNG/srtm2stl/geo/resultado/'
        
        # millimeters
        size_block_x = 190.* 7
        size_block_y = 190.* 5
        size_block_z = 190.
        # dimensionless
        h_scale = 1.0 / 100000.0
        z_scale = 1.0 / 25000.0
        
        raster = MDS(filePath, outPutPath, size_block_x, size_block_y, size_block_z,
                     h_scale, z_scale)
        
        raster_blocks = raster.createRasterBlocks()
        
        for i in raster_blocks:
            s_raster = gdal.Open(i)
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
        
            ul = [s_origin_x, s_origin_y]
            lr = pixel2Coord(s_colls, s_rows, geotransform)
        
            x_extension = calcBlockSize(ul[0], lr[0], h_scale, size_block_x, m2mm)
            y_extension = calcBlockSize(ul[1], lr[1], h_scale, size_block_x, m2mm)
        
            params = {}
            params['s_colls'] = s_colls
            params['s_rows'] = s_rows
            params['s_origin_x'] = 0
            params['s_origin_y'] = y_extension
            params['s_pixel_width'] = x_extension / s_colls
            params['s_pixel_height'] = -y_extension / s_rows
            params['s_x_rotation'] = geotransform[2]
            params['s_y_rotation'] = geotransform[4]
        
            grid = (grid * m2mm) * z_scale

            stl_file_name = os.path.join(
                outPutPath, '%s.stl' % os.path.basename(i)[:-4])
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