from sys import stderr
from optparse import OptionParser

from Bloch import load, save

parser = OptionParser(usage="""%prog <input file> <tolerance> <output file> [<tolerance> <output file>]+

Example:

  %prog counties.shp 500 counties-simple.shp 5000 counties-simpler.shp

That is all.""")

parser.set_defaults()

parser.add_option('-v', '--verbose', dest='verbose',
                  help='Be louder than normal',
                  action='store_true')

if __name__ == '__main__':
    opts, args = parser.parse_args()
    
    infile, outargs = args[0], args[1:]
    outfiles = [(int(outargs[i]), outargs[i + 1]) for i in range(0, len(outargs), 2)]
    
    if opts.verbose:
        print >> stderr, 'Loading data...'

    datasource = load(infile, opts.verbose)
    
    if opts.verbose:
        print >> stderr, len(datasource._indexes()), 'shapes,',
        print >> stderr, datasource.db.execute('SELECT COUNT(DISTINCT line_id) FROM segments').fetchone()[0], 'lines,',
        print >> stderr, datasource.db.execute('SELECT COUNT(DISTINCT guid) FROM segments').fetchone()[0], 'segments.'
    
    for (tolerance, outfile) in sorted(outfiles):
    
        if opts.verbose:
            print >> stderr, 'Simplifying linework to %d...' % tolerance

        datasource.simplify(tolerance, opts.verbose)
        
        if opts.verbose:
            print >> stderr, 'Building %s...' % outfile

        save(datasource, outfile)
