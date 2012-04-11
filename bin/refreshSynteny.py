#
# refreshSynteny.py
#
# This script produces a mouse/human synteny mapping from orthology
# and location information in MGI. 
#
# A "synteny block" is a pair of genomic ranges - one in species A 
# and one in species B - deemed to be "equivalent". 
# A "synteny mapping" is a set of synteny blocks that partitions both
# genomes. That is, in each genome, the blocks (a) are non-overlapping
# and (b) cover the genome.
#
# A synteny block has the following information:
#	id
#	orientation (+=same, -=opposite)
# 	chr, start, end for species A
#	chr, start, end for species B
# The two ranges do not include strand, because biologically, the
# blocks represent double-stranded chunks of DNA.
#
# This script builds synteny blocks starting from pairs of orthologs.
#
# Example:
#
# Suppose mouse genes a, b, c are on the + strand of chr 6 from 10 to 11 MB,
# ordered as given. Their human orthologs, A, B, and C, are on the - strand of chr 22
# between 17 and 18.5 MB. We therefore have a synteny block
# comprising mouse 6:10-11MB and human 22:17-18.5MB in the - orientation.
#
# If the strands are the same (both + or both -), the sblock's orientation
# is +. Otherwise (+/- or -/+) the sblock's orientation is -.
#
# Implementation outline.
# 	1. Query MGI (adhoc.infomratics.jax.org) for mouse/human ortholog pairs.
#	(Each row has columns for 2 genes, one mouse and one human).
#	For each gene, include its id, symbol, chromosome coordinates, and strand.
#	Sorted on mouse chromosome+start pos.
#	2. Eliminate overlaps. Scan the rows: remove a row if its start pos is
#	less than the end pos of the previous row. Then sort on human coords and
#	repeat for human genes.
#	3. Assign indexes to the human genes (0..n-1). Then re-sort by mouse coordinates
#	and assign indexes to the mouse genes. (Adds two columns to the table.)
#	4. Scan: generating initial synteny blocks. The result of this pass is a set of blocks that
#	have gaps in between them.
#	5. Massage the blocks. Fills in the gaps by extending neighboring blocks toward
#	each other. Also extends blocks at the starts of chromosomes.
#	6. Write the blocks in InterMine ItemXML format. Each block is written as two
#	SyntenicRegion features (one human, one mouse) with two corresponding  Location
#	objects. The output also includes minimal representations for the Organisms and
#	Chromosomes.
#	
#

import sys
import os
import urllib
import mgiadhoc as db

TAB = "\t"
NL = "\n"

#
MTAXID = 10090
MCHRS = "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 X Y".split()
#
HTAXID = 9606
HCHRS = "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 X Y".split()
#

ofd = sys.stdout
bfd = open('blocks.txt', 'w')

mchr2count = {}
def startBlock(pair):
    """
    Starts a new synteny block from the given ortholog pair.
    Args:
        pair	(dict)	A query result row containing a mouse/human
		ortholog pair.
    Returns:
        A new synteny block:
    """
    ori = (pair['mstrand'] == pair['hstrand']) and +1 or -1
    mchr = pair['mchr']
    n = mchr2count.setdefault(mchr,1)
    mchr2count[mchr] += 1
    bname = "%s_%d" %(mchr, n)
    blockCount = 1
    return [ bname, ori, blockCount, pair.copy() ]

def extendBlock(currPair,currBlock):
    """
    Extends the given synteny block to include the coordinate
    ranges of the given ortholog pair.
    """
    bname,ori,blockCount,pair = currBlock
    currBlock[2] = blockCount+1
    pair['mstart'] = min(pair['mstart'], currPair['mstart'])
    pair['mend']   = max(pair['mend'],   currPair['mend'])
    pair['hstart'] = min(pair['hstart'], currPair['hstart'])
    pair['hend']   = max(pair['hend'],   currPair['hend'])
    pair['iHi'] = currPair['iHi']

def canMerge(currPair,currBlock):
    """
    Returns True iff the given ortholog pair can merge with (and extend)
    the given synteny block.
    """
    if currBlock is None:
        return False
    bname,ori,bcount,cbfields = currBlock
    cori = (currPair['mstrand']==currPair['hstrand']) and 1 or -1
    return currPair['mchr'] == cbfields['mchr'] \
	and currPair['hchr'] == cbfields['hchr'] \
	and ori == cori \
	and currPair['iHi'] == cbfields['iHi']+ori \

def generateBlocks(allPairs, tagPairs=True):
    """
    Scans the pairs, generating synteny blocks.
    """
    blocks = []
    currBlock = None
    for currPair in allPairs:
	if canMerge(currPair,currBlock):
	    extendBlock(currPair,currBlock)
	else:
	    currBlock = startBlock(currPair)
	    blocks.append(currBlock)
	if tagPairs:
	    currPair['block'] = currBlock[0]
    return blocks

def _massageBlocks(blocks, x):
    for i in xrange(len(blocks)-1):
        cbname, cbori, cbcount, cbfields = blocks[i]
	nbname, nbori, nbcount, nbfields = blocks[i+1]
	if i == 0:
	    cbfields[x+'start'] = 1
	if cbfields[x+'chr'] != nbfields[x+'chr']:
	    nbfields[x+'start'] = 1
	else:
	    delta = nbfields[x+'start'] - cbfields[x+'end']
	    epsilon = 1-delta%2
	    cbfields[x+'end']   += delta/2
	    nbfields[x+'start'] -= (delta/2 - epsilon)
    return blocks

def massageBlocks(blocks):
    blocks = _massageBlocks(blocks, 'm')
    blocks.sort(key=lambda b:(b[-1]['hchr'], b[-1]['hstart']))
    blocks = _massageBlocks(blocks, 'h')
    blocks.sort(key=lambda b:(b[-1]['mchr'], b[-1]['mstart']))
    return blocks

def writeBlock(block):
    bname, ori, bcount, fields = block
    ihi = fields['iHi']
    if ori==1:
	ihi -= (bcount-1)
    b = [
      fields['mchr'],
      fields['mstart'],
      fields['mend'],
      fields['hchr'],
      fields['hstart'],
      fields['hend'],
      bname,
      (ori==1 and "+" or "-"),
      bcount,
      fields['iMi'],
      ihi,
    ]
    bfd.write( TAB.join(map(str,b)) + NL )
    writeBlockItems(*(b[0:7]))

def writeBlockItems(mchr,mstart,mend,hchr,hstart,hend,name):
    (mr,ml) = makeSyntenicRegion('mouse',mchr,mstart,mend,name)
    (hr,hl) = makeSyntenicRegion('human',hchr,hstart,hend,name)
    mr['partner'] = hr['id']
    hr['partner'] = mr['id']
    writeItem(mr, SYN_TMPLT)
    writeItem(ml, LOC_TMPLT)
    writeItem(hr, SYN_TMPLT)
    writeItem(hl, LOC_TMPLT)

def writeHeader():
    sys.stdout.write('<?xml version="1.0"?>\n<items>\n')

def writeFooter():
    sys.stdout.write('</items>\n')

def writeItem(r, tmplt):
    sys.stdout.write( tmplt%r )

def queryMgi():
    q = '''
    SELECT distinct
        m1.symbol AS msymbol, 
	mlc.chromosome AS mchr,
	cast(mlc.startCoordinate AS int) AS mstart,
	cast(mlc.endCoordinate AS int) AS mend,
	mlc.strand AS mstrand,
	m2.symbol AS hsymbol,
	ch.chromosome AS hchr,
	cast(mf.startCoordinate AS int) AS hstart,
	cast(mf.endCoordinate AS int) AS hend,
	mf.strand AS hstrand
    FROM 
	hmd_homology hh1, 
	hmd_homology_marker hm1,
	mrk_marker m1, 
	mrk_location_cache mlc,
	hmd_homology hh2, 
	hmd_homology_marker hm2,
	mrk_marker m2,
	map_coord_feature mf,
	map_coordinate mc,
	mrk_chromosome ch
    WHERE hh1._class_key = hh2._class_key
    AND  hh1._homology_key = hm1._homology_key
    AND hm1._marker_key = m1._marker_key
    AND m1._organism_key = 1
    AND m1._marker_key = mlc._marker_key
    AND mlc.startCoordinate is not null
    AND hh2._homology_key = hm2._homology_key
    AND hm2._marker_key = m2._marker_key 
    AND m2._organism_key = 2
    AND m2._marker_key = mf._object_key
    AND mf._map_key = mc._map_key
    AND mc._collection_key = 47
    AND mc._object_key = ch._chromosome_key
    ORDER BY mchr, mstart
    '''
    res = db.sql(q)
    smap = { 'f':'+', 'r':'-', '+':'+', '-':'-' }
    for r in res:
	if r['mend'] < r['mstart']:
	    r['mstart'], r['mend'] = r['mend'], r['mstart']
        r['mstrand'] = smap[r['mstrand']]
	if r['hend'] < r['hstart']:
	    r['hstart'], r['hend'] = r['hend'], r['hstart']
        r['hstrand'] = smap[r['hstrand']]

    return res

ORG_TMPLT = '''
    <item class="Organism" id="%(id)s">
        <attribute name="taxonId" value="%(taxonId)s" />
	</item>
'''

CHR_TMPLT = '''
    <item class="Chromosome" id="%(id)s">
      <reference name="organism" ref_id="%(organism)s"/>
      <attribute name="primaryIdentifier" value="%(primaryIdentifier)s"/>
      </item>
'''

SYN_TMPLT = '''
    <item class="SyntenicRegion" id="%(id)s" >
      <attribute name="symbol" value="%(symbol)s" />
      <attribute name="name" value="%(name)s" />
      <reference name="organism" ref_id="%(organism)s" />
      <reference name="chromosome" ref_id="%(chromosome)s" />
      <reference name="chromosomeLocation" ref_id="%(chromosomeLocation)s" />
      <reference name="partner" ref_id="%(partner)s" />
      </item>
'''

# Note that SyntenyBlocks have coordinates, but NO strand.
LOC_TMPLT = '''
    <item class="Location" id="%(id)s">
      <reference name="feature" ref_id="%(feature)s" />
      <reference name="locatedOn" ref_id="%(locatedOn)s" />
      <attribute name="start" value="%(start)d" />
      <attribute name="end" value="%(end)d" />
      <attribute name="strand" value="0" />
      </item>
'''

CNAME2CID = {}
CID2N = {}
def getClassId(className):
    cid = CNAME2CID.get(className,None)
    if cid is None:
        cid = len(CNAME2CID) + 1
	CNAME2CID[className] = cid
    return cid

def makeId(className):
    cid = getClassId(className)
    n = CID2N.setdefault(cid,1)
    CID2N[cid] = n+1
    return "%d_%d"%(cid,n)

ORGANISMS = {}
def makeOrganism(NAME, TAXID, CHRS):
    oid = makeId('Organism')
    org = {
	'id' : oid,
	'taxonId' : TAXID,
	}
    writeItem(org, ORG_TMPLT)
    chrs = {}
    for c in CHRS:
      cid = makeId('Chromosome')
      chrs[c] = cid
      chr = { 
        'id' : cid,
	'primaryIdentifier' : c,
	'organism' : oid,
	}
      writeItem(chr, CHR_TMPLT)
    ORGANISMS[NAME] = (oid,chrs)

def getOrganismId(orgname):
    return ORGANISMS[orgname][0]

def getChromosomeId(orgname,chr):
    return ORGANISMS[orgname][1][chr]

def makeOrganisms():
    makeOrganism('mouse', MTAXID, MCHRS)
    makeOrganism('human', HTAXID, HCHRS)

def makeSyntenicRegion(org,chr,start,end,bname):
    oid = getOrganismId(org)
    cid = getChromosomeId(org, chr)
    fid = makeId('SyntenicRegion')
    lid = makeId('Location')
    r = {
        'id' : fid,
	'organism' : oid,
	'symbol' : 'SynBlock:mmhs:%s'%bname,
	'name' : 'NCBI Mouse/Human Synteny Block %s' % bname,
	'chromosome' : cid,
	'chromosomeLocation' : lid,
	}
    l = {
	'id' : lid,
	'feature' : fid,
	'locatedOn' : cid,
	'start' : start,
	'end' : end,
        }
    return (r,l)

def main():
    global iHi, iMi
    allPairs = queryMgi()
    
    # pairs are already ordered by mouse chr/start.
    # Scan list. Remove any mouse gene overlaps.
    lastPair = None
    tmp = []
    for pair in allPairs:
        if lastPair and lastPair['mchr'] == pair['mchr'] and lastPair['mend'] > pair['mstart']:
	    continue
	tmp.append(pair)
	lastPair = pair
    allPairs = tmp

    # Sort by human chr/start coords and remove any overlapping genes.
    allPairs.sort(key=lambda x:(x['hchr'], x['hstart']))
    lastPair = None
    tmp = []
    for pair in allPairs:
        if lastPair and lastPair['hchr'] == pair['hchr'] and lastPair['hend'] > pair['hstart']:
	    continue
	tmp.append(pair)
	lastPair = pair
    allPairs = tmp

    # Assign human index order
    for (i, pair) in enumerate(allPairs):
        pair['iHi'] = i

    # re-sort on mouse chr/start coords and assign index
    allPairs.sort(key=lambda x:(x['mchr'], x['mstart']))
    for (i, pair) in enumerate(allPairs):
        pair['iMi'] = i

    # scan the list and generate synteny blocks
    blks = generateBlocks(allPairs)
    blks = massageBlocks(blks)

    # output
    writeHeader()
    makeOrganisms()
    for b in blks:
	writeBlock(b)
    writeFooter()
#
#
if __name__ == "__main__":
    main()