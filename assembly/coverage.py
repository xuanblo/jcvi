#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Provide coverage QC for assembled sequences:
1. plot paired-end reads as curves
2. plot base coverage and mate coverage
3. plot gaps in the sequence (if any)
"""

import os.path as op
import sys
import logging

from collections import defaultdict
from optparse import OptionParser

from jcvi.formats.base import LineFile, must_open
from jcvi.formats.fasta import gaps
from jcvi.formats.sizes import Sizes
from jcvi.formats.posmap import query, bed
from jcvi.formats.bed import BedLine
from jcvi.apps.base import ActionDispatcher, sh, debug
debug()


class Coverage (LineFile):
    """
    Three-column .coverage file, often generated by `genomeCoverageBed -d`
    contigID baseID coverage
    """
    def __init__(self, bedfile, sizesfile):
        from jcvi.apps.command import BDPATH

        coveragefile = bedfile + ".coverage"
        if not op.exists(coveragefile):
            cmd = BDPATH("genomeCoverageBed")
            cmd += " -d -i {0} -g {1}".format(bedfile, sizesfile)
            sh(cmd, outfile=coveragefile)

        filename = coveragefile
        assert filename.endswith(".coverage")

        super(Coverage, self).__init__(filename)
        fp = open(filename)
        for row in fp:
            ctgID, baseID, cov = row.split()
            cov = int(cov)
            self.append(cov)


def main():

    actions = (
        ('posmap', 'QC based on indexed posmap file'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def clone_name(s, ca=False):
    """
    >>> clone_name("120038881639")
    "0038881639"
    >>> clone_name("GW11W6RK01DAJDWa")
    "GW11W6RK01DAJDW"
    """
    if not ca:
        return s[:-1]

    if s[0] == '1':
        return s[2:]
    return s.rstrip('ab')


def bed_to_bedpe(bedfile, bedpefile, pairsbedfile=None, matesfile=None, ca=False):
    """
    This converts the bedfile to bedpefile, assuming the reads are from CA.
    """
    fp = must_open(bedfile)
    fw = must_open(bedpefile, "w")
    if pairsbedfile:
        fwpairs = must_open(pairsbedfile, "w")

    clones = defaultdict(list)
    for row in fp:
        b = BedLine(row)
        name = b.accn
        clonename = clone_name(name, ca=ca)
        clones[clonename].append(b)

    if matesfile:
        fp = open(matesfile)
        libraryline = fp.next()
        # 'library bes     37896   126916'
        lib, name, smin, smax = libraryline.split()
        assert lib == "library"
        smin, smax = int(smin), int(smax)
        logging.debug("Happy mates for lib {0} fall between {1} - {2}".\
                      format(name, smin, smax))

    nbedpe = 0
    nspan = 0
    for clonename, blines in clones.items():
        if len(blines) == 2:
            a, b = blines
            aseqid, astart, aend = a.seqid, a.start, a.end
            bseqid, bstart, bend = b.seqid, b.start, b.end
            print >> fw, "\t".join(str(x) for x in (aseqid, astart - 1, aend,
                bseqid, bstart - 1, bend, clonename))
            nbedpe += 1
        else:
            a, = blines
            aseqid, astart, aend = a.seqid, a.start, a.end
            bseqid, bstart, bend = 0, 0, 0

        if pairsbedfile:
            start = min(astart, bstart) if bstart > 0 else astart
            end = max(aend, bend) if bend > 0 else aend
            if aseqid != bseqid:
                continue

            span = end - start
            if (not matesfile) or (smin <= span <= smax):
                print >> fwpairs, "\t".join(str(x) for x in \
                        (aseqid, start - 1, end, clonename))
                nspan += 1

    fw.close()
    logging.debug("A total of {0} bedpe written to `{1}`.".\
                  format(nbedpe, bedpefile))
    if pairsbedfile:
        fwpairs.close()
        logging.debug("A total of {0} spans written to `{1}`.".\
                      format(nspan, pairsbedfile))


def posmap(args):
    """
    %prog posmap frgscf.sorted scf.fasta scfID

    Perform QC on the selected scfID, generate multiple BED files for plotting.
    """
    p = OptionParser(posmap.__doc__)

    opts, args = p.parse_args(args)

    if len(args) != 3:
        sys.exit(p.print_help())

    frgscffile, fastafile, scf = args

    # fasta
    cmd = "faOneRecord {0} {1}".format(fastafile, scf)
    scffastafile = scf + ".fasta"
    if not op.exists(scffastafile):
        sh(cmd, outfile=scffastafile)

    # sizes
    sizesfile = scffastafile + ".sizes"
    sizes = Sizes(scffastafile).mapping
    scfsize = sizes[scf]
    logging.debug("`{0}` has length of {1}.".format(scf, scfsize))

    # gaps.bed
    gapsbedfile = scf + ".gaps.bed"
    if not op.exists(gapsbedfile):
        args = [scffastafile, "--bed", "--mingap=100"]
        gaps(args)

    # reads frgscf posmap
    posmapfile = scf + ".posmap"
    if not op.exists(posmapfile):
        args = [frgscffile, scf]
        query(args)

    # reads bed
    bedfile = scf + ".bed"
    if not op.exists(bedfile):
        args = [posmapfile]
        bed(args)

    # reads bedpe
    bedpefile = scf + ".bedpe"
    pairsbedfile = scf + ".pairs.bed"
    if not (op.exists(bedpefile) and op.exists(pairsbedfile)):
        bed_to_bedpe(bedfile, bedpefile, pairsbedfile=pairsbedfile, ca=True)

    # base coverage
    basecoverage = Coverage(bedfile, sizesfile)
    pecoverage = Coverage(pairsbedfile, sizesfile)


if __name__ == '__main__':
    main()
