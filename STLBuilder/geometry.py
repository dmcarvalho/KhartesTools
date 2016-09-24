import numpy as np
from geopy.distance import vincenty


def calcNormal(p0, p1, p2):
    '''
    Calcula o vetor normal ao plano definido pelos pontos nao colineares
    p0, p1 e p2.
    '''
    v1 = p1 - p0
    v2 = p2 - p0
    return np.cross(v1, v2)


def calcDistance(p0, p1, factor):
    '''
    Calcula a distancia geodesica entre dois pontos na unidade de medida
    utilizada para impressao 3d.
    '''
    return vincenty(p0, p1).meters * factor


def calcBlockSize(d_min, d_max, scale, sizeBlock, factor):
    '''
    Calcula o tamanho do bloco de impressao em funcao do comprimento real,
    escala e o fator de conversao para unidade de medida utilizada para a
    impressao 3d
    '''
    delta = calcDistance([0, 0], [0, d_max - d_min], factor)
    return (delta * scale)


def validateZScale(d_min, d_max, scale, sizeBlock, factor):
    '''
    Valida se a escala indicada pelo usuario e possivel de ser impressa
    '''
    return (d_max - d_min) * factor * scale < sizeBlock


def getMaxZScale(d_min, d_max, sizeBlock, factor):
    '''
    Calcula a escala otima para impressao
    '''
    return 1 / (((d_max - d_min) * factor) / (sizeBlock))


def pixel2Coord(Xpixel, Yline, geotransform):
        Xgeo = (geotransform[0] + Xpixel *
                geotransform[1] + Yline * geotransform[2] +
                (geotransform[1] + Yline * geotransform[2]) / 2)
        Ygeo = (geotransform[3] + Yline *
                geotransform[5] + Xpixel * geotransform[4] +
                (geotransform[5] + Xpixel * geotransform[4]) / 2)
        return [Xgeo, Ygeo]