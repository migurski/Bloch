from sys import argv, stderr, exit
from osgeo import ogr
from rtree import Rtree
from shapely.geos import lgeos
from shapely.geometry import MultiLineString, LineString, Polygon
from shapely.geometry.base import geom_factory
from shapely.wkb import loads, dumps
from shapely.ops import polygonize
from itertools import combinations, permutations
from sqlite3 import connect

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
    """ Returns a geometry with lines merged using GEOSLineMerge.
    """
    if shape.type != 'MultiLineString':
        return shape
    
    # copied from shapely.ops.linemerge at http://github.com/sgillies/shapely
    result = lgeos.GEOSLineMerge(shape._geom)
    return geom_factory(result)

def linemunge(lines, depth=0):
    """ Similar to linemerge(), but happy to return invalid linestrings.
    """
    joined = False
    indexes = range(len(lines))
    removed = set()
    
    print depth, sum([line.length for line in lines]),
    
    for (i, j) in combinations(indexes, 2):
        if i in removed or j in removed:
            continue
    
        if lines[i].intersects(lines[j]):
            if lines[i].intersection(lines[j]).type in ('Point', 'MultiPoint'):
                print (i, j), 
            
                coordsA = list(lines[i].coords)
                coordsB = list(lines[j].coords)
                
                if coordsA[-1] == coordsB[0]:
                    lines[i] = LineString(coordsA[:-1] + coordsB)

                elif coordsA[-1] == coordsB[-1]:
                    coordsB.reverse()
                    lines[i] = LineString(coordsA[:-1] + coordsB)

                elif coordsB[-1] == coordsA[0]:
                    lines[i] = LineString(coordsB[:-1] + coordsA)

                elif coordsB[-1] == coordsA[-1]:
                    coordsA.reverse()
                    lines[i] = LineString(coordsB[:-1] + coordsA)

                else:
                    print 'wait',
                    continue
                
                lines[j] = None
                removed.add(j)
                joined = True
    
    lines = [line for line in lines if line is not None]
    
    print 'to', sum([line.length for line in lines]), 'in', len(lines), 'lines'

    if joined:
        lines = linemunge(lines, depth + 1)
    else:
        print [(map(int, coords[0]), map(int, coords[-1])) for coords in [list(line.coords) for line in lines]]
        print depth, 'done.'
    
    return lines

def simplify(original_shape, tolerance, cross_check):
    """
    """
    if original_shape.type != 'LineString':
        return original_shape
    
    coords = list(original_shape.coords)
    new_coords = coords[:]
    
    if len(coords) <= 2:
        # don't shorten the too-short
        return original_shape
    
    # For each coordinate that forms the apex of a three-coordinate
    # triangle, find the area of that triangle and put it into a list
    # along with the coordinate index and the resulting line if the
    # triangle were flattened, ordered from smallest to largest.

    triples = [(i + 1, coords[i], coords[i + 1], coords[i + 2]) for i in range(len(coords) - 2)]
    triangles = [(i, Polygon([c1, c2, c3, c1]), c1, c3) for (i, c1, c2, c3) in triples]
    areas = sorted( [(triangle.area, i, c1, c3) for (i, triangle, c1, c3) in triangles] )

    min_area = tolerance ** 2
    
    if areas[0][0] > min_area:
        # there's nothing to be done
        return original_shape
    
    if cross_check:
        rtree = Rtree()
    
        # We check for intersections by building up an R-Tree index of each
        # and every line segment that makes up the original shape, and then
        # quickly doing collision checks against these.
    
        for j in range(len(coords) - 1):
            (x1, y1), (x2, y2) = coords[j], coords[j + 1]
            rtree.add(j, (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    
    preserved, popped = set(), False
    
    # Remove any coordinate that makes a triangle whose area is
    # below the minimum threshold, starting with the smallest and
    # working up. Mark points to be preserved until the recursive
    # call to simplify().
    
    for (area, index, ca, cb) in areas:
        if area > min_area:
            # there won't be any more points to remove.
            break
    
        if index in preserved:
            # the current point is too close to a previously-preserved one.
            continue
        
        preserved.add(index + 1)
        preserved.add(index - 1)

        if cross_check:
        
            # This is potentially a very expensive check, so we use the R-Tree
            # index we made earlier to rapidly cut down on the number of lines
            # from the original shape to check for collisions.
        
            (x1, y1), (x2, y2) = ca, cb
            new_line = LineString([ca, cb])

            box_ids = rtree.intersection((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            old_lines = [LineString(coords[j:j+2]) for j in box_ids]
            
            # Will removing this point result in an invalid geometry?

            if True in [old_line.crosses(new_line) for old_line in old_lines]:
                # Yes, because the index told us so.
                continue

            if new_line.crosses(original_shape):
                # Yes, because we painstakingly checked against the original shape.
                continue
        
        # It's safe to remove this point
        new_coords[index], popped = None, True
    
    new_coords = [coord for coord in new_coords if coord is not None]
    
    if cross_check:
        print 'simplify', len(coords), 'to', len(new_coords)
    
    if not popped:
        return original_shape
    
    return simplify(LineString(new_coords), tolerance, cross_check)

print >> stderr, 'Loading data...'

datasource = load_datasource(argv[1])
indexes = range(len(datasource.values))

# guid, src1_id, src2_id, line_id, x1, y1, x2, y2

db = connect(':memory:').cursor()

db.execute("""CREATE table segments (
                
                -- global identifier for this segment
                guid    INTEGER PRIMARY KEY AUTOINCREMENT,

                -- identifiers for source shape or shapes for shared borders
                src1_id INTEGER,
                src2_id INTEGER,
                
                -- global identifier for this line
                line_id INTEGER,
                
                -- start and end coordinates for this segment
                x1      REAL,
                y1      REAL,
                x2      REAL,
                y2      REAL

              )""")

rtree = Rtree()

print >> stderr, 'Making shared borders...'

line_id = 0
graph, shared = {}, [[] for i in indexes]
comparison, comparisons = 0, len(indexes)**2 / 2

for (i, j) in combinations(indexes, 2):

    shape1 = datasource.shapes[i]
    shape2 = datasource.shapes[j]
    
    if shape1.intersects(shape2):
        print >> stderr, '%.2f%% -' % (100. * comparison/comparisons),
        print >> stderr, 'feature #%d and #%d' % (i, j),
        
        border = shape1.intersection(shape2)
        
        geoms = hasattr(border, 'geoms') and border.geoms or [border]
        
        print >> stderr, sum( [len(list(g.coords)) for g in geoms] ), 'coords',
        
        for geom in geoms:
            coords = list(geom.coords)
            segments = [coords[i:i+2] for i in range(len(coords) - 1)]
            
            for ((x1, y1), (x2, y2)) in segments:
                db.execute("""INSERT INTO segments
                              (src1_id, src2_id, line_id, x1, y1, x2, y2)
                              VALUES (?, ?, ?, ?, ?, ?, ?)""",
                           (i, j, line_id, x1, y1, x2, y2))
                
                # rtree.insert(-----, (
            
            line_id += 1
        

        graph[(i, j)] = True
        shared[i].append(border)
        shared[j].append(border)
        
        print >> stderr, '-', border.type

    comparison += 1

for row in db.execute('SELECT * FROM segments LIMIT 20'):
    print row

exit() #------------------------------------------------------------------------

print >> stderr, 'Making unshared borders...'

unshared = []

for i in indexes:

    boundary = datasource.shapes[i].boundary
    
    for border in shared[i]:
        boundary = boundary.difference(border)

    unshared.append(boundary)

print >> stderr, 'Checking lengths...'

for i in indexes:

    shared_lengths = [border.length for border in shared[i]]
    
    tolerance, error = 0.000001, abs(datasource.shapes[i].length - unshared[i].length - sum(shared_lengths))
    assert error < tolerance, 'Feature #%(i)d error too large: %(error).8f > %(tolerance).8f' % locals()

exit()

print >> stderr, 'Building output...'

err_driver = ogr.GetDriverByName('ESRI Shapefile')
err_source = err_driver.CreateDataSource('err.shp')
assert err_source is not None, 'Failed creation of err.shp'
err_layer = err_source.CreateLayer('default', datasource.srs, ogr.wkbMultiLineString)

out_driver = ogr.GetDriverByName('ESRI Shapefile')
out_source = out_driver.CreateDataSource('out.shp')
assert out_source is not None, 'Failed creation of out.shp'
out_layer = out_source.CreateLayer('default', datasource.srs, ogr.wkbMultiPolygon)

for field in datasource.fields:
    for a_layer in (out_layer, err_layer):
        field_defn = ogr.FieldDefn(field.name, field.type)
        field_defn.SetWidth(field.width)
        a_layer.CreateField(field_defn)

tolerance = 650

for i in indexes:

    # Build up a list of linestrings that we will attempt to polygonize.

    parts = shared[i] + [unshared[i]]
    lines = []
    
    for part in parts:
        for geom in getattr(part, 'geoms', None) or [part]:
            if geom.type == 'LineString':
                lines.append(geom)

    try:
        # Try simplify without cross-checks because it's cheap and fast.
        simple_lines = [simplify(line, tolerance, False) for line in lines]
        line_lengths = int(sum([l.length for l in simple_lines]))

        poly = polygonize(simple_lines).next()
        
        if poly.length < line_lengths:
            raise StopIteration

    except StopIteration:
        # A polygon wasn't found, for one of two reasons we're interested in:
        # the shape would be too small to show up with the given tolerance, or
        # the simplification resulted in an invalid, self-intersecting shape.
        
        lost_area = datasource.shapes[i].area
        lost_portion = lost_area / (tolerance ** 2)
        
        if lost_portion < 4:
            # It's just small.
            print >> stderr, 'Skipped small feature #%(i)d' % locals()
            continue

        # A large lost_portion is a warning sign that we have an invalid polygon.
        
        try:
            def assemble(polygons, depth=0):
                """
                """
                popped = True
                
                while popped:
                
                    popped = False
                    removed = set()
                    indexes = range(len(polygons))
                    
                    for (i, j) in permutations(indexes, 2):
                        if i in removed or j in removed:
                            continue
                        
                        if polygons[i].contains(polygons[j]):
                            try:
                                poly1, poly2 = polygons[i], polygons[j]

                                exterior = list(poly1.exterior.coords)
                                interiors = [list(r.coords) for r in poly1.interiors]
                                interiors += [list(poly2.exterior.coords)]

                                polygons[i] = Polygon(exterior, interiors)
                            except Exception, e:
                                print i, '=', i, '-', j, '= Error', e
                                pass
                            else:
                                print i, '=', i, '-', j
                                popped = True
                            removed.add(j)
                            polygons[j] = None
                
                    polygons = [poly for poly in polygons if poly is not None]
                
                return polygons
        
            def polygulate(lines):
                """
                """
                munged_lines = linemunge(lines[:])
                
                print len(munged_lines), 'lines?'
                line_coords = [list(line.coords) for line in munged_lines]
                poly_coords = [c for c in line_coords if c[0] == c[-1] and len(c) >= 3]
                print len(poly_coords), 'polygons?'
                polygons = [Polygon(coords) for coords in poly_coords]
                
                print len(polygons), 'polygons'
                yield assemble(polygons)[0]
            
                raise StopIteration
        
            # Try simplify again with cross-checks because it's slow but careful.
            simple_lines = [simplify(line, tolerance, False) for line in lines]
            try:
                poly = polygulate(simple_lines).next()
            except Exception, e:
                print e
                raise StopIteration

        except StopIteration:
            # Again no polygon was found, which now probably means we have
            # an actual error that should be saved to the error output file.
    
            #raise Warning('Lost feature #%(i)d, %(lost_portion)d times larger than maximum tolerance' % locals())
            print >> stderr, 'Lost feature #%(i)d, %(lost_portion)d times larger than maximum tolerance' % locals()
    
            feat = ogr.Feature(err_layer.GetLayerDefn())
            
            for (j, field) in enumerate(datasource.fields):
                feat.SetField(field.name, datasource.values[i][j])
            
            multiline = MultiLineString([list(line.coords) for line in simple_lines])
            
            geom = ogr.CreateGeometryFromWkb(dumps(multiline))
            
            feat.SetGeometry(geom)
        
            err_layer.CreateFeature(feat)
            
            continue
        
    #
    
    feat = ogr.Feature(out_layer.GetLayerDefn())
    
    for (j, field) in enumerate(datasource.fields):
        feat.SetField(field.name, datasource.values[i][j])
    
    geom = ogr.CreateGeometryFromWkb(dumps(poly))
    
    feat.SetGeometry(geom)

    out_layer.CreateFeature(feat)
