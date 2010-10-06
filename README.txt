Bloch - Simplify linework in polygonal geographic datasources.

DESCRIPTION

    Inspired by Matthew Bloch's MapShaper thesis (http://mapshaper.org), Bloch can
    load OGR-compatible data sources and simplify the linework while preserving
    topology. The simplify() method accepts tolerances in map units, so
    simplification can be performed by known amounts with predictable outcomes.
    
    Dependencies include Warmerdam (http://trac.osgeo.org/gdal/wiki/GdalOgrInPython)
    and Gillies (http://trac.gispython.org/lab/wiki/Rtree, http://trac.gispython.org/lab/wiki/Shapely).
    
    Example usage:
    
      # Load a data file into a Datasource instance.
      datasrc = load('input.json')
      
      # Simplify the geometry.
      datasrc.simplify(500)
      
      # Save it out to a new shapefile.
      save(datasrc, 'output1.shp')
      
      # This will throw an error, because 250 < 500.
      datasrc.simplify(250)
      
      # Simplify the geometry more.
      datasrc.simplify(1000)
      
      # Save it out to a new GeoJSON file.
      save(datasrc, 'output2.json')

CLASSES
    Datasource
    
    class Datasource
     |  Store an exploded representation of a data source, so it can be simplified.
     |  
     |  Methods defined here:
     |  
     |  __init__(self, srs, geom_type, fields, values, shapes)
     |      Use load() to call this constructor.
     |  
     |  simplify(self, tolerance, verbose=False)
     |      Simplify the polygonal linework.
     |      
     |      This method can be called multiple times, but the process is
     |      destructive so it must be called with progressively increasing
     |      tolerance values.

FUNCTIONS
    load(filename, verbose=False)
        Load an OGR data source, return a new Datasource instance.
    
    save(datasource, filename)
        Save a Datasource instance to a named OGR datasource.

