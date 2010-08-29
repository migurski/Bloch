from sys import argv, exit
from osgeo import ogr
from shapely.wkb import loads, dumps
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
    def __init__(self, srs, geom_type, fields, features, shapes):
        self.srs = srs
        self.fields = fields
        self.geom_type = geom_type
        self.features = features
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

    features, shapes = [], []
    
    for feature in layer:
        features.append(feature)
    
        shape = loads(feature.geometry().ExportToWkb())
        shapes.append(shape)

    return Datasource(srs, geom_type, fields, features, shapes)

datasource = load_datasource(argv[1])
indexes = range(len(datasource.features))

shared = {}

for (i, j) in combinations(indexes, 2):

    feature1 = datasource.features[i]
    feature2 = datasource.features[j]
    
    shape1 = datasource.shapes[i]
    shape2 = datasource.shapes[j]
    
    if shape1.intersects(shape2):
        print feature1.GetField(4), 'and', feature2.GetField(4),
        
        border = shape1.intersection(shape2)
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
    
    print datasource.features[i].GetField(4),
    print datasource.shapes[i].geom_type, int(datasource.shapes[i].length),
    print '=', unshared[i].geom_type, int(unshared[i].length),
    print '+', map(int, shared_lengths),
    print '=', int(unshared[i].length + sum(shared_lengths))
    
    tolerance, error = 0.000001, abs(datasource.shapes[i].length - unshared[i].length - sum(shared_lengths))
    assert error < tolerance, 'Error too large: %(error).8f > %(tolerance).8f' % locals()

print '\n'.join(dir(ogr))
print '-' * 80
print '-' * 40

driver = ogr.GetDriverByName('ESRI Shapefile')
source = driver.CreateDataSource('out.shp')
newlayer = source.CreateLayer('default', datasource.srs, datasource.geom_type)

for field in datasource.fields:
    field_defn = ogr.FieldDefn(field.name, field.type)
    field_defn.SetWidth(field.width)
    newlayer.CreateField(field_defn)

feat = ogr.Feature(newlayer.GetLayerDefn())
feat.SetField('County', 'Hello World')

geom = ogr.CreateGeometryFromWkb(dumps(datasource.shapes[0]))

feat.SetGeometry(geom)

newlayer.CreateFeature(feat)
