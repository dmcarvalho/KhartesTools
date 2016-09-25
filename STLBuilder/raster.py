from osgeo import gdal
import numpy as np
import os
from geometry import pixel2Coord, calcBlockSize
from subprocess import call


noDataValue = -9999
m2mm = 1000.0


class MDS():
    def __init__(self, file_path,
                 size_block_x,
                 size_block_y, size_block_z,
                 h_scale, z_scale, output_path=None):

        self._raster = gdal.Open(file_path)
        self._output_path = output_path
        self._size_block_x = size_block_x
        self._size_block_y = size_block_y
        self._size_block_z = size_block_z
        self._h_scale = h_scale
        self._z_scale = z_scale

        self._geotransform = self._raster.GetGeoTransform()
        self._driver = self._raster.GetDriver()

        self._band = self._raster.GetRasterBand(1)
        self._grid = self._band.ReadAsArray()

        self._origin_x = self._geotransform[0]  # decimal degree
        self._origin_y = self._geotransform[3]  # decimal degree
        self._pixel_width = self._geotransform[1]
        self._pixel_height = self._geotransform[5]

        self._colls = self._raster.RasterXSize
        self._rows = self._raster.RasterYSize

        self._z_min = np.min(self._grid)
        self._z_max = np.max(self._grid)

        self._ul = [self._origin_x, self._origin_y]
        self._lr = self.pixelOffset2coord(self._colls, self._rows)

        self._x_extension = calcBlockSize(self._ul[0], self._lr[0],
                                          self._h_scale,
                                          self._size_block_x, m2mm)
        self._y_extension = calcBlockSize(self._ul[1], self._lr[1],
                                          self._h_scale,
                                          self._size_block_x, m2mm)

        self.step_x = None
        self.step_y = None

        self.num_block_lines = None
        self.num_block_columns = None
        self.block_files = []

    def setStepX(self, step):
        self.step_x = step

    def setStepY(self, step):
        self.step_y = step

    def setNumBlockLines(self, numLines):
        self.num_block_lines = numLines

    def setNumBlockColunms(self, numColumns):
        self.num_block_columns = numColumns

    def pixelOffset2coord(self, Xpixel, Yline):
        return pixel2Coord(Xpixel, Yline, self._geotransform)

    def raster2array(self, band):
        band = self._raster.GetRasterBand(band)
        array = band.ReadAsArray()
        return array

    def createRaster(self, params, dataType=None, zeroAsNoData=False, band=1):
        band = self._raster.GetRasterBand(band)
        if not dataType:
            dataType = band.DataType
        # todo validar se shape do array igual aos parametros da imagem
        outputRasterPath = os.path.join(self._output_path, 'temp.tif')
        target_ds = self._driver.Create(outputRasterPath,
                                        params['s_colls'],
                                        params['s_rows'],
                                        1,
                                        dataType)
        target_ds.SetGeoTransform((params['s_origin_x'],
                                   params['s_pixel_width'],
                                   params['s_x_rotation'],
                                   params['s_origin_y'],
                                   params['s_y_rotation'],
                                   params['s_pixel_height']))

        target_ds.SetProjection(self._raster.GetProjectionRef())

        array = np.ones((params['s_rows'], params['s_colls'])) * self._z_min

        outband = target_ds.GetRasterBand(1)
        outband.SetNoDataValue(noDataValue)
        if zeroAsNoData:
            array[array == 0] = noDataValue
        outband.WriteArray(array)
        outband.WriteArray(self._grid, params['offset_x'], params['offset_x'])

        outband.FlushCache()
        return target_ds

    def createRasterWithNewExtent(self):
        '''
        calcula a nova dimensao a ser imprimida de forma que\
        existam somente blocos inteiros

        '''
        dX = (self._pixel_width * self._colls)
        fator_x = ((int(self._x_extension / self._size_block_x) + 1) *
                   self._size_block_x) / self._x_extension
        n_r_size_x = dX * fator_x
        dif_p_x = int((n_r_size_x - dX) / self._pixel_width) + 1
        offset_x = int(dif_p_x / 2)

        new_origin_x = self._origin_x - offset_x * self._pixel_width
        new_colls = self._colls + dif_p_x
        new_pixel_width = self._pixel_width

        dY = (self._pixel_height * self._rows)
        fator_y = ((int(self._y_extension / self._size_block_y) + 1) *
                   self._size_block_y) / self._y_extension
        n_r_size_y = dY * fator_y
        dif_p_y = int((n_r_size_y - dY) / self._pixel_height) + 1
        offset_y = int(dif_p_y / 2)

        new_origin_y = self._origin_y - offset_y * (self._pixel_height)
        new_rows = self._rows + dif_p_y
        new_pixel_height = self._pixel_height

        params = {}
        params['s_colls'] = new_colls
        params['s_rows'] = new_rows
        params['s_origin_x'] = new_origin_x
        params['s_origin_y'] = new_origin_y
        params['s_pixel_width'] = new_pixel_width
        params['s_pixel_height'] = new_pixel_height
        params['s_x_rotation'] = self._geotransform[2]
        params['s_y_rotation'] = self._geotransform[4]
        params['offset_x'] = offset_x
        params['offset_y'] = offset_y

        ul = [new_origin_x, new_origin_y]
        lr = pixel2Coord(new_colls, new_rows, self._geotransform)

        x_extension = calcBlockSize(
            ul[0], lr[0], self._h_scale, self._size_block_x, m2mm)
        y_extension = calcBlockSize(
            ul[1], lr[1], self._h_scale, self._size_block_x, m2mm)

        self.setStepX((new_pixel_width * new_colls) /
                      int(x_extension / self._size_block_x))
        self.setStepY((new_pixel_height * new_rows) /
                      int(y_extension / self._size_block_y))

        self.setNumBlockLines(int(y_extension / self._size_block_y))
        self.setNumBlockColunms(int(x_extension / self._size_block_x))

        self.params = params
        #return self.createRaster(params)

    def createRasterBlocks(self):
        self.block_files = []
        new_raster = self.createRasterWithNewExtent()
        new_file_path = new_raster.GetFileList()[0]

        geotransform = new_raster.GetGeoTransform()
        s_origin_x = geotransform[0]  # decimal degree
        s_origin_y = geotransform[3]  # decimal degree
        new_raster = None
        for j in range(self.num_block_lines):
            for i in range(self.num_block_columns):
                ul_x = s_origin_x + i * self.step_x
                ul_y = s_origin_y + j * self.step_y
                lr_x = ul_x + self.step_x
                lr_y = ul_y + self.step_y

                block_name = os.path.join(
                    self._output_path, '%s_%s.tif' % (j, i))
                comando_dem = 'gdal_translate -projwin %s %s %s %s -of GTiff %s %s' % (
                    ul_x, ul_y, lr_x, lr_y, new_file_path, block_name)
                print comando_dem
                call(comando_dem, shell=True)
                self.block_files.append(block_name)
        return self.block_files
