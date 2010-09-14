from sys import argv, stderr, exit
from osgeo import ogr
from rtree import Rtree
from rtree.core import RTreeError
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
                        y2      REAL,
                        
                        -- flag
                        removed INTEGER
        
                      )""")
        
        db.execute('CREATE INDEX segments_lines ON segments (line_id, guid)')
        db.execute('CREATE INDEX shape1_lines ON segments (src1_id, line_id, guid)')
        db.execute('CREATE INDEX shape2_lines ON segments (src2_id, line_id, guid)')
        
        self.db = db
        self.rtree = Rtree()

    def indexes(self):
        return range(len(self.values))

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

def populate_shared_segments(datasource):
    """
    """
    shared = [[] for i in datasource.indexes()]
    comparison, comparisons = 0, len(datasource.indexes())**2 / 2
    
    for (i, j) in combinations(datasource.indexes(), 2):
    
        shape1 = datasource.shapes[i]
        shape2 = datasource.shapes[j]
        
        if shape1.intersects(shape2):
            print >> stderr, '%.2f%% -' % (100. * comparison/comparisons),
            print >> stderr, 'feature #%d and #%d' % (i, j),
            
            border = linemerge(shape1.intersection(shape2))
            
            geoms = hasattr(border, 'geoms') and border.geoms or [border]
            
            print >> stderr, sum( [len(list(g.coords)) for g in geoms] ), 'coords',
            
            for geom in geoms:
                try:
                    line_id = datasource.rtree.count(datasource.rtree.get_bounds())
                except RTreeError:
                    line_id = 0
        
                print >> stderr, '-', 'line', line_id,
        
                coords = list(geom.coords)
                segments = [coords[k:k+2] for k in range(len(coords) - 1)]
                
                for ((x1, y1), (x2, y2)) in segments:
                    datasource.db.execute("""INSERT INTO segments
                                             (src1_id, src2_id, line_id, x1, y1, x2, y2, removed)
                                             VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                                          (i, j, line_id, x1, y1, x2, y2))
                    
                    bbox = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
                    datasource.rtree.add(datasource.db.lastrowid, bbox)
            
            shared[i].append(border)
            shared[j].append(border)
            
            print >> stderr, '-', border.type
    
        comparison += 1

    return shared

def populate_unshared_segments(datasource, shared):
    """
    """
    for i in datasource.indexes():
    
        boundary = datasource.shapes[i].boundary
        
        for border in shared[i]:
            boundary = boundary.difference(border)
        
        print >> stderr, i, boundary.type,
    
        geoms = hasattr(boundary, 'geoms') and boundary.geoms or [boundary]
        geoms = [geom for geom in geoms if hasattr(geom, 'coords')]
        
        for geom in geoms:
            try:
                line_id = datasource.rtree.count(datasource.rtree.get_bounds())
            except RTreeError:
                line_id = 0
    
            print >> stderr, '-', 'line', line_id,
    
            coords = list(geom.coords)
            segments = [coords[k:k+2] for k in range(len(coords) - 1)]
            
            for ((x1, y1), (x2, y2)) in segments:
                datasource.db.execute("""INSERT INTO segments
                                         (src1_id, line_id, x1, y1, x2, y2, removed)
                                         VALUES (?, ?, ?, ?, ?, ?, 0)""",
                                      (i, line_id, x1, y1, x2, y2))
                
                bbox = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
                datasource.rtree.add(datasource.db.lastrowid, bbox)
    
        print >> stderr, '.'

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

print >> stderr, 'Making shared borders...'
shared_borders = populate_shared_segments(datasource)

print >> stderr, 'Making unshared borders...'
populate_unshared_segments(datasource, shared_borders)

print len(datasource.indexes()), 'shapes.'
print datasource.rtree.count(datasource.rtree.get_bounds()), 'guids (rtree).'
print datasource.db.execute('SELECT COUNT(DISTINCT guid) FROM segments').fetchone()[0], 'guids (db).'
print datasource.db.execute('SELECT COUNT(DISTINCT line_id) FROM segments').fetchone()[0], 'lines? (db)'
print datasource.db.execute('SELECT COUNT(DISTINCT src1_id), COUNT(DISTINCT src2_id) FROM segments').fetchone(), 'shapes? (db)'

tolerance = 500

line_ids = [line_id for (line_id, ) in datasource.db.execute('SELECT DISTINCT line_id FROM segments')]

while True:

    was = datasource.db.execute('SELECT COUNT(*) FROM segments WHERE removed=0').fetchone()[0]
    
    preserved, popped = set(), False
    
    for line_id in line_ids:
        
        rows = datasource.db.execute("""SELECT guid, x1, y1, x2, y2
                                        FROM segments
                                        WHERE line_id = ?
                                          AND removed = 0
                                        ORDER BY guid""",
                                     (line_id, ))
        
        pairs = [(guid, (x1, y1), (x2, y2)) for (guid, x1, y1, x2, y2) in rows]
        triples = [(pairs[i][0], pairs[i+1][0], pairs[i][1], pairs[i][2], pairs[i+1][2]) for i in range(len(pairs) - 1)]
        triangles = [(guid1, guid2, Polygon([c1, c2, c3, c1]), c1, c3) for (guid1, guid2, c1, c2, c3) in triples]
        areas = sorted( [(triangle.area, guid1, guid2, c1, c3) for (guid1, guid2, triangle, c1, c3) in triangles] )
        
        min_area = tolerance ** 2
        
        if not areas or areas[0][0] > min_area:
            continue
        
        for (area, guid1, guid2, ca, cb) in areas:
            if area > min_area:
                break
            
            if guid1 in preserved or guid2 in preserved:
                continue
    
            preserved.add(guid1)
            preserved.add(guid2)
            
            def bbox(x1, y1, x2, y2):
                return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            
            (x1, y1), (x2, y2) = ca, cb
            new_line = LineString([ca, cb])
    
            old_guids = datasource.rtree.intersection(bbox(x1, y1, x2, y2))
            old_rows = datasource.db.execute('SELECT x1, y1, x2, y2 FROM segments WHERE guid IN (%s)' % ','.join(map(str, old_guids)))
            old_lines = [LineString([(x1, y1), (x2, y2)]) for (x1, y1, x2, y2) in old_rows]
            
            if True in [new_line.crosses(old_line) for old_line in old_lines]:
                stderr.write('x%d' % line_id)
                continue
            
            popped = True
            
            for guid in (guid1, guid2):
                q = 'SELECT x1, y1, x2, y2 FROM segments WHERE guid = %d' % guid
                x1, y1, x2, y2 = datasource.db.execute(q).fetchone()
                datasource.rtree.delete(guid, bbox(x1, y1, x2, y2))
    
            x1, y1, x2, y2 = ca[0], ca[1], cb[0], cb[1]
    
            datasource.db.execute('UPDATE segments SET removed=1 WHERE guid=%d' % guid2)
            datasource.db.execute('UPDATE segments SET x1=?, y1=?, x2=?, y2=? WHERE guid=?',
                                  (x1, y1, x2, y2, guid1))
    
            datasource.rtree.add(guid1, bbox(x1, y1, x2, y2))
        
        stderr.write('.')
    
    print >> stderr, ' reduced from', was, 'to',
    print >> stderr, datasource.db.execute('SELECT COUNT(*) FROM segments WHERE removed=0').fetchone()[0]
        
    if not popped:
        break

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

for i in datasource.indexes():

    segments = datasource.db.execute("""SELECT x1, y1, x2, y2
                                        FROM segments
                                        WHERE (src1_id = ? OR src2_id = ?)
                                          AND removed = 0""", (i, i))

    lines = [LineString([(x1, y1), (x2, y2)]) for (x1, y1, x2, y2) in segments]
    
    try:
        poly = polygonize(lines).next()

    except StopIteration:
        lost_area = datasource.shapes[i].area
        lost_portion = lost_area / (tolerance ** 2)
        
        if lost_portion < 4:
            # It's just small.
            print >> stderr, 'Skipped small feature #%(i)d' % locals()
            continue

        raise Exception('yow')
    
    print i, poly.length, 'vs.', sum([line.length for line in lines])
    
    feat = ogr.Feature(out_layer.GetLayerDefn())
    
    for (j, field) in enumerate(datasource.fields):
        feat.SetField(field.name, datasource.values[i][j])
    
    geom = ogr.CreateGeometryFromWkb(dumps(poly))
    
    feat.SetGeometry(geom)

    out_layer.CreateFeature(feat)
