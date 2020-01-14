import re
import string
import sys

DIGIT_PROG = re.compile(r"\d+")
PUNCT_PROG = re.compile(r"[{}]".format(string.punctuation))
SPACE_PROG = re.compile(r"\s+")


class SegmentDeduplifier:
    """Deduplify sentence pairs using Tilde's approach (Tilde 2018)
       Along with a few others."""

    def __init__(self, case=False):
        self._set = set()
        self._case = case

    def preprocess(self, segment):
        if not self._case:
            segment = segment.lower()
        segment = DIGIT_PROG.sub("0", segment)
        segment = PUNCT_PROG.sub(" ", segment)
        segment = SPACE_PROG.sub(" ", segment)
        return segment

    def is_unique(self, segment):
        key = self.preprocess(segment)
        is_unique = key not in self._set
        self._set.add(key)
        return is_unique


class TSVDeduplifier:
    """Deduplify CSV such that each field must be unique."""

    def __init__(self, case=False):
        self._segment_deduplifiers = [SegmentDeduplifier(case=case) for _ in range(100)]

    def is_unique(self, line):
        segments = line.strip("\n").split("\t")
        is_unique = True
        for (deduplifier, segment) in zip(self._segment_deduplifiers, segments):
            is_unique = is_unique and deduplifier.is_unique(segment)
        return is_unique

def comm_naive(file_keep, file_remove, invert=False, fuzzy=False, case=False):
    deduplifier = SegmentDeduplifier(case=case)
    def split_and_preprocess(line):
        parts = line.strip("\n").split("\t")
        if fuzzy:
            parts =  [deduplifier.preprocess(part) for part in parts]
        return list(parts)

    segments = set()
    with file_keep.open("r") as fp:
        for line in fp:
            segments.update(split_and_preprocess(line))

    with file_remove.open("r") as fp:
        for line in fp:
            has_common_field = set(split_and_preprocess(line)).intersection(segments)
            should_print = has_common_field if not invert else not has_common_field
            if should_print:
                sys.stdout.write(line)  # has newline


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

    file2.add_argument(
        "file_remove", metavar="file2", type=path_filetype, help="Path to file"
    )

    opts.add_argument(
        "-v",
        dest="invert",
        action="store_true",
        help="Invert output. I.e. behave as a band-stop filter rather than band-pass filter.",
    )
    opts.add_argument(
        "--fuzzy",
        dest="fuzzy",
        action="store_true",
        help="Fuzzy match over punctuation and numbers.",
    )
    opts.add_argument(
        "--case",
        dest="case",
        action="store_true",
        help="Use case-sensitive comparison",
    )

    args = parser.parse_args()

    comm_naive(
        args.file_keep,
        args.file_remove,
        args.invert,
        args.fuzzy,
        args.case,
    )


if __name__ == "__main__":
    main()

