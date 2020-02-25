#!/usr/bin/env python3
"""
    Reynir: Natural language processing for Icelandic

     Module/component title

    Copyright (C) 2020 Miðeind ehf.

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
    Extract parallel sentences from a tmx file

    Usage:
    process_ees.py \
        -i /path/to/input_file \
        -o /path/to/output_file \
        -s EN-GB \
        -t IS-IS

    File format: (line numbers are not part of file)
      1 <?xml version='1.0' encoding='UTF-8'?><tmx version="1.4">
      2  <header adminlang="EN-GB" creationtool="LF Aligner" creationtoolversion="3.11" datatype="unkno
      3   </header>
      4  <body>
      5     <tu creationdate="20180910T110521Z" creationid="LF Aligner 3.11">
      6       <prop type="fileId">31960R0011</prop><prop type="Txt::Note">-0.0648649</prop>
      7       <tuv xml:lang="EN-GB"><seg>Regulation No 11 concerning the abolition of discrimination in
      8       <tuv xml:lang="IS-IS"><seg>tengslum við framkvæmd 3. mgr. 79. gr. stofnsáttmála Efnahagsb
      9     </tu>
     10     <tu creationdate="20180910T110521Z" creationid="LF Aligner 3.11">
     11       <prop type="fileId">31960R0011</prop><prop type="Txt::Note">0.86087</prop>
     12       <tuv xml:lang="EN-GB"><seg>Whereas Article 79 (3) requires the Council to lay down rules
     13       <tuv xml:lang="IS-IS"><seg>Samkvæmt 3. mgr. 79. gr. ber ráðinu að setja reglur um afnám á
     14     </tu>
     15     <tu creationdate="20180910T110521Z" creationid="LF Aligner 3.11">
     16       <prop type="fileId">31960R0011</prop><prop type="Txt::Note">1.13947</prop>
     17       <tuv xml:lang="EN-GB"><seg>Whereas such abolition requires the prohibition of the above-m
     18       <tuv xml:lang="IS-IS"><seg>Þetta afnám felur í sér bann við mismunun í þeirri mynd sem að
     19     </tu>

    ...
"""

import os
import xml.etree.cElementTree as ET
from pathlib import Path

_SPEC = "{http://www.w3.org/XML/1998/namespace}"
_LANG_SPEC = "{spec}lang".format(spec=_SPEC)


class TMXFile:
    def __init__(self, path):
        self._path = path
        self._tree = ET.parse(str(self._path))
        self._root = None
        self._src_lang = None
        self._tgt_lang = None
        self._langs = None

    @property
    def root(self):
        if not self._root:
            self._root = self._tree.getroot()
        return self._root

    @property
    def src_lang(self):
        if not self._src_lang:
            header = self.root.find("header")
            self._src_lang = header.attrib.get("srclang")
        return self._src_lang

    @property
    def langs(self):
        if not self._langs:
            langs = []
            slang = self.src_lang
            first_tu = self.root.find(".//tu")
            for tuv in first_tu.iter("tuv"):
                lang = tuv.attrib.get(_LANG_SPEC, None)
                langs.append(lang)
            other_langs = [lang for lang in langs if lang != slang]
            tlang = other_langs[0]
            self._langs = [slang, tlang]
        return self._langs

    def bitext(self, swap=False):
        slang, tlang = self.langs
        for trnsl_unit in self.root.iterfind("./body/tu"):
            variants = trnsl_unit.findall("tuv")[:2]

            src_seg = variants[0].find("seg").text
            tgt_seg = variants[1].find("seg").text
            if variants[0].attrib.get(_LANG_SPEC) != self.src_lang:
                src_seg, tgt_seg = tgt_seg, src_seg
            if swap:
                src_seg, tgt_seg = tgt_seg, src_seg
            ret = [src_seg, tgt_seg]

            yield ret


def path_filetype(path_string):
    from pathlib import Path
    path = Path(path_string)
    return path.resolve() if path.resolve().exists() else None


def main(src_file, tgt_file):
    tmx = TMXFile(src_file)
    with tgt_file.open("w", encoding="utf8") as out_file:
        for row in tmx.bitext():
            out_file.write("\t".join(row) )
            out_file.write("\n")


if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser((
        "Extracts parallel sentences from tmx file and writes to output file in a .tsv format."
        "Where first column is srclang as defined in teiHeader."
    ))
    parser.add_argument(
        "src_path", type=path_filetype, help="Input file"
    )
    parser.add_argument(
        "tgt_path", nargs="?", default=None, help="Output file"
    )

    args = parser.parse_args()

    out_path = Path(__file__).resolve().with_name((args.src_path.with_suffix(".tsv").name))
    if args.tgt_path is None:
        out_path = Path(os.getcwd()) / args.src_path.with_suffix(".tsv").name
    elif Path(args.tgt_path).resolve().is_dir():
        out_path = Path(args.tgt_path).resolve() / args.src_path.with_suffix(".tsv").name
    main(
        args.src_path,
        out_path,
    )
