import osgeo.gdal as gdal
import numpy as np
import os

from geometry import pixel2Coord, calcBlockSize, calcNormal
from raster import MDS
from stl_writer import StlWriter

from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtCore import pyqtSlot
# QGIS imports


FORM_CLASS, _ = uic.loadUiType(os.path.join(
os.path.dirname(__file__), 'STLBuilder.ui'))






class STLBuilder(QtGui.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(STLBuilder, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
    
    @pyqtSlot()    
    def on_buttonBox_accepted(self):
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
        
        import time
        
        start = time.time()
        
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
        
                    # print v1,v2,v3
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
        
        
        end = time.time() - start
        print end
