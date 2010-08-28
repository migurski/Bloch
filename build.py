from sys import argv, exit
from osgeo import ogr
from shapely.wkb import loads
from itertools import combinations

print argv

source = ogr.Open(argv[1])
layer = source.GetLayer(0)

print layer.GetFeatureCount(), 'features'
#print layer.GetSpatialRef()

features, shapes = [], []

for i in range(layer.GetFeatureCount()):
    feature = layer.GetNextFeature()
    features.append(feature)

    shape = loads(feature.geometry().ExportToWkb())
    shapes.append(shape)

shared = {}

for (i, j) in combinations(range(len(features)), 2):

    feature1 = features[i]
    feature2 = features[j]
    
    shape1 = shapes[i]
    shape2 = shapes[j]
    
    if shape1.intersects(shape2):
        print feature1.GetField(4), 'and', feature2.GetField(4),
        
        border = shape1.intersection(shape2)
        shared[(i, j)] = border
        
        print '-', border.geom_type, int(border.length)

unshared = []

for i in range(len(features)):

    boundary = shapes[i].boundary
    
    for (key, border) in shared.items():
        if i in key:
            boundary = boundary.difference(border)

    unshared.append(boundary)

for i in range(len(features)):

    border_lengths = [border.length for (key, border) in shared.items() if i in key]
    
    print features[i].GetField(4),
    print shapes[i].geom_type, int(shapes[i].length),
    print '=', unshared[i].geom_type, int(unshared[i].length),
    print '+', map(int, border_lengths),
    print '=', int(unshared[i].length + sum(border_lengths))
