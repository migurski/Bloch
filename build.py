from sys import argv, exit
from osgeo import ogr
from shapely.wkb import loads, dumps
from shapely.geometry import LineString, MultiLineString
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

def join_multiline_parts(shape):
    """
    """
    if shape.geom_type != 'MultiLineString':
        return shape
    
    lines = [LineString(list(geom.coords)) for geom in shape.geoms]
    
    i = 0
    
    while i < len(lines) - 1:
        if lines[i].touches(lines[i + 1]):
            c1, c2 = list(lines[i].coords), list(lines.pop(i + 1).coords)
            lines[i] = LineString(c1 + c2[1:])

        else:
            i += 1

    return MultiLineString([list(line.coords) for line in lines])

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
        
        border = join_multiline_parts(shape1.intersection(shape2))
        shared[(i, j)] = border
        
        print '-', border.geom_type, int(border.length)

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
    print datasource.shapes[i].geom_type, int(datasource.shapes[i].length),
    print '=', unshared[i].geom_type, int(unshared[i].length),
    print '+', map(int, shared_lengths),
    print '=', int(unshared[i].length + sum(shared_lengths))
    
    tolerance, error = 0.000001, abs(datasource.shapes[i].length - unshared[i].length - sum(shared_lengths))
    assert error < tolerance, 'Error too large: %(error).8f > %(tolerance).8f' % locals()

driver = ogr.GetDriverByName('ESRI Shapefile')
source = driver.CreateDataSource('out.shp')
newlayer = source.CreateLayer('default', datasource.srs, ogr.wkbLineString)

for field in datasource.fields:
    field_defn = ogr.FieldDefn(field.name, field.type)
    field_defn.SetWidth(field.width)
    newlayer.CreateField(field_defn)

for (i, shape) in enumerate(unshared):
    if shape.geom_type not in ('LineString', 'MultiLineString'):
        continue

    feat = ogr.Feature(newlayer.GetLayerDefn())
    
    for (j, field) in enumerate(datasource.fields):
        feat.SetField(field.name, datasource.values[i][j])
    
    geom = ogr.CreateGeometryFromWkb(dumps(shape))
    
    feat.SetGeometry(geom)

    newlayer.CreateFeature(feat)

    if shape.geom_type == 'MultiLineString':
        print len(shape.geoms), datasource.values[i][4]
