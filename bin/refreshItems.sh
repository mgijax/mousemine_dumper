#!/bin/sh
python ./dumpMgiItemXml.py -d ../output/mgi-base -Dmoshfile=../output/obo/MOSH.obo --logfile ./LOG
if [ $? -ne 0 ] 
then
    exit -1 
fi
python ./idChecker.py ../output/mgi-base
if [ $? -ne 0 ] 
then
    exit -1 
fi
