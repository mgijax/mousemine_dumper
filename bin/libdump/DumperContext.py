from common import *
import mgiadhoc as db
import time

class DumperContext:

    class ItemError(RuntimeError):
        pass

    class DuplicateIdError(ItemError):
        pass

    class DanglingReferenceError(ItemError):
        pass

    def __init__(self, debug=False, dir=".", limit=None, defs={}, logfile=None, logconsole=True, checkRefs=True):
	self.debug=debug
	self.dir = dir
	self.limit=limit
	self.fname = None
	self.checkRefs = checkRefs
	self.fd = sys.stdout
	if logfile:
	    self.logfile = os.path.abspath(os.path.join(os.getcwd(), logfile))
	    self.logfd = open(self.logfile, 'a')
	else:
	    self.logfile = "<stderr>"
	    self.logfd = sys.stderr
	self.consolefd = None
	if logconsole and self.logfd is not sys.stderr:
	    self.consolefd = sys.stderr
	self.QUERYPARAMS = {
	    # MGItype keys
	    'REF_TYPEKEY' : 1,
	    'MARKER_TYPEKEY' : 2,
	    'ALLELE_TYPEKEY' : 11,
	    'TERM_TYPEKEY' : 13,
	    'ORGANISM_TYPEKEY' : 20,
	    'CHROMOSOME_TYPEKEY' : 27,

	    # Organism keys
	    'MOUSE_ORGANISMKEY' : 1,
	    'HUMAN_ORGANISMKEY' : 2,
	    'RAT_ORGANISMKEY' : 40,

	    # Logical database keys
	    'MGI_LDBKEY' : 1,
	    'TAXONOMY_LDBKEY' : 32,
	    'PUBMED_LDBKEY' : 29,
	    'ENTREZ_LDBKEY' : 55,

	    # Coordinate maps
	    'HUMAN_MAPKEY' : 47,

	    # Nomen status values (from MRK_Status)
	    'OFFICIAL_STATUS' : 1,

	    #
	    'TAXAIDS' : COMMA.join(map(lambda o:"'%d'"%o, TAXAIDS)),
	    'LIMIT_CLAUSE' : limit and (' LIMIT %d '%limit) or '',

	    #
	    'ORGANISMKEYS' : '1,2,40',	# default=mouse,human,rat.
	    }

	# Keys from ACC_MGIType.
	# Maps type name to type key
	self.TYPE_KEYS = self.loadMgiTypeKeys()
	# Add other types that we need to output
	self.TYPE_KEYS.update({
	    'Homologue'			: 10001,
	    'OrthologueEvidence'	: 10002,
	    'OrthologueEvidenceCode'	: 10003,
	    'Location'			: 10004,
	    'GenotypeAllelePair'	: 10005,
	    'OntologyAnnotation'	: 10006,
	    'OntologyAnnotationEvidence': 10007,
	    'OntologyAnnotationEvidenceCode': 10008,
	    'Synonym'			: 10009,
	    'DataSource'		: 10010,
	    'DataSet'			: 10011,
	    'CrossReference'		: 10012,
	    'Author'			: 10013,
	    'SOTerm'			: 10014,
	    })

	# map integer type ids to type names
	self.TK2TNAME = dict(map(lambda x: (x[1],x[0]), self.TYPE_KEYS.items()))

	# Maps type name to next-id for allocating IDs.
	# Generally, for a given type, either all IDs are generated
	# or all IDs are constructed from existing MGI keys.
	self.NEXT_ID = { }

	#
	# Keep track of item ids that have been written out.
	#
	self.idsWritten = set()

	# apply command-line definitions to the context
	for n,v in defs.iteritems():
	    if not hasattr(self,n):
		setattr(self, n, v)

	#
	# Keep track of files open for output
	# dict : filename -> filedescriptor
	#
	self.outfiles = {}

    # Loads type information from ACC_MGIType.
    #
    def loadMgiTypeKeys(self):
	tkeys = {}
        q = '''
	    SELECT _mgitype_key, name
	    FROM ACC_MGIType
	    '''
	for r in db.sql(q):
	    tkeys[r['name']] = r['_mgitype_key']
	return tkeys

    # Given a type name and an integer key unique within that 
    # type, creates a globally unique string key of the form
    # "n_m", where n is the type's integer key and
    # m is the input key. The returned val
    #
    def makeGlobalKey(self, itemType, localkey=None, exists=None):
	if localkey is None:
	    localkey = self.NEXT_ID.setdefault(itemType, 1001)
	    self.NEXT_ID[itemType] += 1
	elif localkey < 0:
	    # Ugh. We can't use negative keys. MGI often uses -1 for
	    # Not Specified and -2 for Not Applicable. 
	    # Crude hackery: add 10000000 to the key (i.e., allocate
	    # negative keys in a region we HOPE won't clash with
	    # real keys.
	    localkey += 10000000
	if type(itemType) is types.StringType:
	    itemType = self.TYPE_KEYS[itemType]
	key = '%d_%d' % (itemType,localkey)
	if self.checkRefs and exists is True and key not in self.idsWritten:
	    raise DumperContext.DanglingReferenceError(key)
	elif exists is False and key in self.idsWritten:
	    raise DumperContext.DuplicateIdError(key)
	else:
	    return key

    def makeItemId(self, itemType, localKey=None):
        return self.makeGlobalKey(itemType, localKey, False)

    def makeItemRef(self, itemType, localKey):
        return self.makeGlobalKey(itemType, localKey, True)

    # Wrapper that logs sql queries.
    #
    def sql(self, q, p=None, args={}):
	self.log(str(q))
        return db.sql(q, p, args=args)

    def openOutput(self, fname):
	if self.fd and not self.fd.closed:
	    self.fd.flush()
        self.fname = os.path.abspath(os.path.join(self.dir, fname))
        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
	self.fd = self.outfiles.get(self.fname, None)
	if self.fd is None:
	    # open a new output file
	    self.fd = open(self.fname, 'w')
	    self.outfiles[self.fname]=self.fd
	    self.fd.write('<?xml version="1.0"?>\n')
	    self.fd.write('<items>\n')

    def writeOutput(self, id, s):
	self.idsWritten.add( id )
        self.fd.write(s)

    def closeOutputs(self):
	for fname,fd in self.outfiles.items():
	    fd.write('\n</items>\n')
	    fd.close()

    def log(self, s, timestamp=True, newline=True):
	newline = newline and "\n" or ""
	timestamp = timestamp and ("%s :: "%time.asctime()) or ""
	msg = "%s%s%s" % (timestamp, s, newline)
	self.logfd.write(msg)
	self.logfd.flush()
	if self.consolefd:
	    self.consolefd.write(msg)
	    self.consolefd.flush()

    def installSamplers(self, samplermodule):
        for n in dir(samplermodule):
	    x = getattr(samplermodule,n)
	    if type(x) is types.FunctionType:
		print n
	        pass
