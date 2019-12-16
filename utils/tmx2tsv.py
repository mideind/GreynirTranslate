#!/usr/bin/env python3
"""
    Reynir: Natural language processing for Icelandic

     Module/component title

    Copyright (C) 2019 Miðeind ehf.

       This program is free software: you can redistribute it and/or modify
       it under the terms of the GNU General Public License as published by
       the Free Software Foundation, either version 3 of the License, or
       (at your option) any later version.
       This program is distributed in the hope that it will be useful,
       but WITHOUT ANY WARRANTY; without even the implied warranty of
       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
       GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see http://www.gnu.org/licenses/.

     Module/component description

"""

"""
    Usage:  ./parse_tmx.py --file $INPATH --src_lang ice --tgt_lang --dest $OUTPATH

    Expected format of input file

    <?xml version="1.0" encoding="utf-8"?>
    <tmx version="1.4">
      <header creationtool="Moses-to-TMX-converer" creationtoolversion="1.0" 
          o-tmf="Moses plain text files" datatype="plaintext" segtype="sentence" 
          adminlang="EN-US" srclang="en" creationdate="20170426T083707Z">
      </header>
      <body>
        <tu>
          <tuv xml:lang="en">
            <seg>&quot; based on published data</seg>
          </tuv>
          <tuv xml:lang="is">
            <seg>&quot; samkvæmt birtum niðurstöðum</seg>
          </tuv>
        </tu>
        <tu>
          <tuv xml:lang="en">
            <seg>&quot; HbA1c (%) at week 24.</seg>
          </tuv>
          <tuv xml:lang="is">
            <seg>&quot; HbA1c (%) í 24. viku.</seg>
          </tuv>
        </tu>
    ...
"""

import sys
import xml.etree.cElementTree as ET

LANG_SPEC = "{http://www.w3.org/XML/1998/namespace}"

def main(filepath_in, filepath_out, src_lang, tgt_lang):
    tree = ET.parse(filepath_in)
    root = tree.getroot()

    with open(filepath_out, 'w') as out_file:
        for tu in root.iterfind('./body/tu'):
            tuvs = tu.findall('tuv')
            src_text = tuvs[0].find('seg').text
            tgt_text = tuvs[1].find('seg').text
            if tuvs[0].attrib['%slang' % LANG_SPEC] != src_lang:
                src_text, tgt_text = tgt_text, src_text
            out_str = '{}\t{}\n'.format(src_text, tgt_text)
            out_file.write(out_str)

if __name__ == "__main__":
    import argparse, os

    parser = argparse.ArgumentParser('Reads moses tmx from file and writes tabbed version to destination file.')
    parser.add_argument('-f', '--file', dest='FILE_PATH_IN', required=True, help="Path to file that is to be converted.")
    parser.add_argument('-d', '--dest', dest='FILE_PATH_OUT', required=True, help="Path to output file.")
    parser.add_argument('-s', '--src_lang', dest='SRC_LANG', required=True, help="Source language.")
    parser.add_argument('-t', '--tgt_lang', dest='TGT_LANG', required=True, help="Target language.")
    args = parser.parse_args()
    if not os.path.exists(args.FILE_PATH_IN):
        raise argparse.ArgumentError("File does not exist")
    main(args.FILE_PATH_IN, args.FILE_PATH_OUT, args.SRC_LANG, args.TGT_LANG)
