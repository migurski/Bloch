from sys import argv, exit
from osgeo import ogr
from shapely.geos import lgeos
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import geom_factory
from shapely.wkb import loads, dumps
from shapely.ops import polygonize
from itertools import combinations

class Field:
    """
    """
    def __init__(self, name, type, width):
        self.name = name
        self.type = type
        self.width = width

class Datasource:
    """
    """
    def __init__(self, srs, geom_type, fields, values, shapes):
        self.srs = srs
        self.fields = fields
        self.geom_type = geom_type
        self.values = values
        self.shapes = shapes

def load_datasource(filename):
    """
    """
    source = ogr.Open(filename)

    layer = source.GetLayer(0)
    srs = layer.GetSpatialRef()
    layer_defn = layer.GetLayerDefn()
    geom_type = layer_defn.GetGeomType()
    
    fields = [Field(field_defn.GetNameRef(), field_defn.GetType(), field_defn.GetWidth())
              for field_defn 
              in [layer_defn.GetFieldDefn(i) for i in range(layer_defn.GetFieldCount())]]

    values, shapes = [], []
    
    for feature in layer:
        values.append([feature.GetField(field.name) for field in fields])
        shapes.append(loads(feature.geometry().ExportToWkb()))

    return Datasource(srs, geom_type, fields, values, shapes)

def linemerge(shape):
    """
    """
    if shape.type != 'MultiLineString':
        return shape
    
    # copied from shapely.ops.linemerge at http://github.com/sgillies/shapely
    result = lgeos.GEOSLineMerge(shape._geom)
    return geom_factory(result)

def simplify(shape, tolerance, depth=0):
    """
    """
    if shape.type != 'LineString':
        return shape
    
    coords = list(shape.coords)
    
    if len(coords) <= 2:
        # don't shorten the too-short
        return shape
    
    # For each coordinate that forms the apex of a three-coordinate
    # triangle, find the area of that triangle and put it into a list
    # along with the coordinate index, ordered from smallest to largest.

    triples = [(i + 1, coords[i], coords[i + 1], coords[i + 2]) for i in range(len(coords) - 2)]
    triangles = [(i, Polygon([c1, c2, c3, c1])) for (i, c1, c2, c3) in triples]
    areas = sorted( [(triangle.area, i) for (i, triangle) in triangles] )
    
    preserved, min_area = set(), tolerance ** 2
    
    if areas[0][0] > min_area:
        # there's nothing to be done
        return shape
    
    # Remove any coordinate that makes a triangle whose area is
    # below the minimum threshold, starting with the smallest and
    # working up. Mark points to be preserved until the recursive
    # call to simplify().

    for (area, index) in areas:
        if area > min_area:
            break
    
        if index in preserved:
            continue
        
        coords[index] = None
        preserved.add(index + 1)
        preserved.add(index - 1)
    
    coords = [coord for coord in coords if coord is not None]
    return simplify(LineString(coords), tolerance, depth + 1)

datasource = load_datasource(argv[1])
indexes = range(len(datasource.values))

shared = {}

for (i, j) in combinations(indexes, 2):

    feature1 = datasource.values[i]
    feature2 = datasource.values[j]
    
    shape1 = datasource.shapes[i]
    shape2 = datasource.shapes[j]
    
    if shape1.intersects(shape2):
        print feature1[4], 'and', feature2[4],
        
        border = linemerge(shape1.intersection(shape2))
        shared[(i, j)] = border
        
        print '-', border.type, int(border.length), len(getattr(border, 'geoms', [None]))

unshared = []

for i in indexes:

    boundary = datasource.shapes[i].boundary
    
    for (key, border) in shared.items():
        if i in key:
            boundary = boundary.difference(border)

    unshared.append(boundary)

for i in indexes:

    shared_lengths = [border.length for (key, border) in shared.items() if i in key]
    
    print datasource.values[i][4],
    print datasource.shapes[i].type, int(datasource.shapes[i].length),
    print '=', unshared[i].type, int(unshared[i].length),
    print '+', map(int, shared_lengths),
    print '=', int(unshared[i].length + sum(shared_lengths))
    
    tolerance, error = 0.000001, abs(datasource.shapes[i].length - unshared[i].length - sum(shared_lengths))
    assert error < tolerance, 'Error too large: %(error).8f > %(tolerance).8f' % locals()

driver = ogr.GetDriverByName('ESRI Shapefile')
source = driver.CreateDataSource('out.shp')
newlayer = source.CreateLayer('default', datasource.srs, ogr.wkbPolygon)

for field in datasource.fields:
    field_defn = ogr.FieldDefn(field.name, field.type)
    field_defn.SetWidth(field.width)
    newlayer.CreateField(field_defn)

tolerance = 500 # 650 is a problem for co2000p020-CA-merc.shp

for i in indexes:

    #

    parts = [border for (key, border) in shared.items() if i in key] + [unshared[i]]
    lines = []
    
    for part in parts:
        for geom in getattr(part, 'geoms', None) or [part]:
            if geom.type == 'LineString':
                lines.append(simplify(geom, tolerance))

    try:
        poly = polygonize(lines).next()
    except StopIteration:
        # I guess this one doesn't get included
        print 'Skip', i, (tolerance ** 2), 'vs.', datasource.shapes[i].area, (datasource.shapes[i].area / (tolerance ** 2))
        continue

    #
    
    feat = ogr.Feature(newlayer.GetLayerDefn())
    
    for (j, field) in enumerate(datasource.fields):
        feat.SetField(field.name, datasource.values[i][j])
    
    geom = ogr.CreateGeometryFromWkb(dumps(poly))
    
    feat.SetGeometry(geom)

    newlayer.CreateFeature(feat)
