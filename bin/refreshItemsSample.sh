#!/bin/sh
#python ./dumpMgiItemXml.py -d ../output/mgi-sample -Dmoshfile=/Users/jer/work/mouseminedata/output/obo/MOSH.obo --logfile ./LOG --install Sampler
python ./dumpMgiItemXml.py -d ../output/mgi-sample -Dmoshfile=${MM_DATA}/output/obo/MOSH.obo --logfile ./LOG --install Sampler