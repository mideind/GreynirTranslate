"""
    Reynir: Natural language processing for Icelandic

     comm_csv

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

     This module implements a "comm"-like feature  (the gnu program) 
     but for tsv files, and over fields instead of whole lines.
"""

import sys


def index_lines_in_file(path, fields):
    fields_idxs = [i - 1 for i in fields]
    lines = []
    table = {idx: dict() for idx in fields}
    with open(str(path), "r", encoding="utf8") as fp:
        for (line_idx, line) in enumerate(fp):
            fields = line.strip("\n").split("\t")
            lines.append(line)
            for field_idx in fields_idxs:
                table[field_idx][fields[field_idx]] = line_idx
    return lines, table


def get_line_intersections(lines, table, path, fields2):
    fields1_idxs = list(table.keys())
    fields2_idxs = [i - 1 for i in fields2]
    lines = []
    file1_idxs = set()
    file2_idxs = set()
    with open(str(path), "r", encoding="utf8") as fp:
        for (line_idx, line) in enumerate(fp):
            fields = line.strip("\n").split("\t")
            lines.append(line)
            for i1, i2 in zip(fields1_idxs, fields2_idxs):
                field = fields[i2]
                if field in table[i1]:
                    file1_idxs.add(table[i1][field])
                    file2_idxs.add(line_idx)
    return file1_idxs, file2_idxs


def comm_csv(file_keep, fields_keep, file_remove, fields_remove, index_left=True):
    items = [(file_keep, fields_keep ), (file_remove, fields_remove )]
    pair1, pair2 = items if index_left else reversed(items)
    file1, fields1 = pair1
    file2, fields2 = pair2

    lines, table = index_lines_in_file(file1, fields1)
    idxs_1, idxs_2 = get_line_intersections(lines, table, file2, fields2)

    idxs = idxs_2
    if index_left:
        idxs = idxs_1

    with open(file_remove, "r", "utf8") as fp:
        for (idx, line) in enumerate(fp):
            if idx in idxs:
                sys.stdout.write(line)  # has newline


def comma_separated_ints(arg_string):
    ints = set(int(i) for i in arg_string.split(","))
    return ints


def path_filetype(path_string):
    from pathlib import Path

    path = Path(path_string)
    return path if path.exists() else None


def main():
    import argparse

    try:
        import argcomplete
    except ImportError as e:
        pass
    parser = argparse.ArgumentParser(
        (
            "Compare two files and remove lines with fields in common in second file."
            "The supplied fields for each file must be equal in number."
        )
    )

    file1 = parser.add_argument_group("File that keeps lines with fields in common")
    file2 = parser.add_argument_group("File that removes lines with fields in common")
    opts = parser.add_argument_group("Optionals:")
    file1.add_argument(
        "file_keep", metavar="file1", type=path_filetype, help="Path to file"
    )
    file1.add_argument(
        "fields_keep",
        metavar="fields",
        type=comma_separated_ints,
        help="Comma separated list of fields (integers, 1-indexed)",
    )

    file2.add_argument(
        "file_remove", metavar="file2", type=path_filetype, help="Path to file"
    )

    fields_arg = file2.add_argument(
        "fields_remove",
        metavar="fields",
        type=comma_separated_ints,
        help="Comma separated list of fields (integers)",
    )

    opts.add_argument(
        "-r",
        dest="index_right",
        action="store_true",
        help="Use right-side file path for indexing rather than the left",
    )


    args = parser.parse_args()
    parser.print_help()
    if len(args.fields_remove) != len(args.fields_keep):
        raise argparse.ArgumentError(fields_arg, "Fields must be equal in number")
    elif any(i < 1 for i in args.fields_remove.union(args.fields_remove)):
        print(args.fields_remove, args.fields_remove)
        raise argparse.ArgumentError(fields_arg, "Fields must be equal greater or equal to 1")

    comm_csv(args.file_keep, args.fields_keep, args.file_remove, args.fields_remove, not args.index_right):


if __name__ == "__main__":
    main()
