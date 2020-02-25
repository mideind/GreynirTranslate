#!/usr/bin/env python3
"""
    Reynir: Natural language processing for Icelandic

     Filter pipeline

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

     Filter pipeline with various filters for text.

"""


import collections
import functools
import json
import os
import re
import sys
import time

# from langid.langid import LanguageIdentifier, model
# import pycld2 as cld2

import editdistance

from symbols import (
    SYMBOL_WHITELIST,
    BANNED_SYMBOLS,
    SUBSTITUTE_FOR_NULL,
    PUNCTUATION_SYMBOLS,
    QUOTE_LIKE,
    ICE_QUOTE,
)

import tokenizer

_PROJECT_DIR = os.path.dirname(os.path.realpath("__file__"))
_ENIS_VOCAB_PATH = "/home/haukur/github/Reynir/resources/vocab.enis.16384.subwords"
_TMP_DIR = "/tmp/filters"

T2T_AVAILABLE = True
try:
    from tensor2tensor.data_generators import text_encoder
except ImportError:
    print("Running without tensor2tensor", file=sys.stderr)
    T2T_AVAILABLE = False

ENC = None

# LANGID_IDENTIFIER = LanguageIdentifier.from_modelstring(model, norm_probs=True)
# LANGID_IDENTIFIER.set_languages(["en", "is"])
# LANGID_IDENTIFIER = None
# if LANGID_IDENTIFIER is None:
#     LANGID_IDENTIFIER = LanguageIdentifier.from_modelstring(model, norm_probs=True)

MAX_SUBTOKENS_PER_SENTENCE = 256
MAX_CHARS_PER_SENTENCE = 500
BANNED_SYMBOLS_PAT = "[" + re.escape(BANNED_SYMBOLS) + "]"
DEFAULT_MIN_WORD_COUNT = 3


class Example:
    def __init__(self, src, tgt, file_id=None, align_score=None):
        self.source = src
        self.target = tgt
        self.file_id = file_id
        self.align_score = align_score

    def __str__(self):
        return "\t".join([self.source, self.target])

    def __repr__(self):
        ret = [self.source, self.target, self.file_id, self.align_score]
        return "[" + "\t".join(ret) + "]"


def print_ex(ex):
    print("\t".join([ex["en"], ex["is"]]))


def get_or_initialize_encoder():
    global ENC
    if ENC is None:
        ENC = text_encoder.SubwordTextEncoder(_ENIS_VOCAB_PATH)
    return ENC


# def probably_correct_language(text, lang_code, lower_bound=0.8):
#     isReliable, bytesFound, *rest = list(cld2.detect(text.lower()))
#     langName, langCode, prob, _ = rest[0][0]
#     if isReliable and langCode == langCode and prob > 80:
#         return True
#     # msg = "{0:<8.7f}  {1}/{2}  {3}".format(prob, langCode, lang_code, text)
#     # print(msg)
#     return False


class Deduplifier:
    """Deduplify sentence pairs using Tilde's approach (Tilde 2018)
       Along with a few others."""

    _set = set()

    @classmethod
    def preprocess_sentence(cls, sentence):
        digit_prog = RegexCache.compile_rx(r"\d+")
        punct_prog = RegexCache.compile_rx("[" + re.escape(PUNCTUATION_SYMBOLS) + "]")
        space_prog = RegexCache.compile_rx(r"\s+")
        sentence = sentence.lower()
        sentence = digit_prog.sub("0", sentence)
        sentence = punct_prog.sub("", sentence)
        sentence = space_prog.sub("", sentence)
        return sentence

    @classmethod
    def preprocess_example(cls, ex):
        ice, eng = ex["is"], ex["en"]
        ice = cls.preprocess_sentence(ice)
        eng = cls.preprocess_sentence(eng)
        return eng + "\t" + ice

    @classmethod
    def is_unique_example(cls, ex):
        key = cls.preprocess_example(ex)
        if key in cls._set:
            return False
        cls._set.add(key)
        return True

    @classmethod
    def is_unique_example(cls, ex):
        key = cls.preprocess_example(ex)
        if key in cls._set:
            return False
        cls._set.add(key)
        return True


class Transformations:
    """Transformations of examples to be used in a pipeline"""

    _transforms = {}  # registered transformations

    @classmethod
    def apply(cls, name, ex):
        if name not in cls._transforms:
            raise KeyError("Could not find transformation {0}".format(name))
        else:
            return cls._transforms[name](ex)

    @classmethod
    def register(cls, fun):
        if fun.__name__ not in cls._transforms:
            cls._transforms[fun.__name__] = fun
        else:
            raise ValueError(
                "Tried to register transform {0} more than once".format(fun.__name__)
            )


class RegexCache:
    _programs = {}  # compiled regular expressions

    @classmethod
    def compile_rx(cls, pattern):
        if pattern not in cls._programs:
            program = re.compile(pattern)
            cls._programs[pattern] = program
        return cls._programs[pattern]


class Filters:

    _programs = {}  # compiled regular expressions
    _filters = {}  # registered filters

    @classmethod
    def register(cls, fun):
        if fun.__name__ not in cls._filters:
            cls._filters[fun.__name__] = fun
        else:
            raise ValueError(
                "Tried to register filter {0} more than once".format(fun.__name__)
            )

    @classmethod
    def apply(cls, filter_name, ex, inverted=False):
        if filter_name not in cls._filters:
            raise KeyError("Could not find filter {0}".format(filter_name))
        else:
            res = cls._filters[filter_name](ex)
            return not res if inverted else res


def register_filter(fun):
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        return fun(*args, **kwargs)

    Filters.register(fun)
    return wrapper


def register_transformation(fun):
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        return fun(*args, **kwargs)

    Transformations.register(fun)
    return wrapper


@register_transformation
def fix_ice_quotes(ex):
    ice, eng = ex["is"], ex["en"]
    ice = ice.replace(  # 0x201d  RIGHT DOUBLE QUOTATION MARK
        "”", ICE_QUOTE.PRIMARY.RIGHT
    )

    if not bool(set(ICE_QUOTE.PRIMARY.BOTH) & set(ice)):
        ice = ice.replace(ICE_QUOTE.SECONDARY.LEFT, ICE_QUOTE.PRIMARY.LEFT)
        ice = ice.replace(ICE_QUOTE.SECONDARY.RIGHT, ICE_QUOTE.PRIMARY.RIGHT)

    return {"is": ice, "en": eng}


@register_transformation
def fix_improper_line_split(ex):
    ice_prog = RegexCache.compile_rx(r"(\b(?!\d)\w+)- (\b(?!eða|og)\w+\b)")
    eng_prog = RegexCache.compile_rx(r"(\b(?!\d)\w+)- (\b(?!or|and)\w+\b)")
    ice = ice_prog.sub(r"\1\2", ex["is"])
    eng = eng_prog.sub(r"\1\2", ex["en"])
    return {"is": ice, "en": eng}


@register_transformation
def remove_leading_bullet(ex):
    ice, eng = ex["is"], ex["en"]
    # bullet, hyphen-minus, n-dash, horizontal bar
    prog = RegexCache.compile_rx(r"(^(• ?|- |– |― |\.\s?)+)")
    sice = prog.sub("", ice)
    seng = prog.sub("", eng)
    return {"is": sice, "en": seng}


@register_transformation
def replace_dashes(ex):
    ice, eng = ex["is"], ex["en"]
    # hyphen, n-dash, horizontal bar, m-dash, minus sign, figure dash
    prog = RegexCache.compile_rx(r"(‐|–|―|—|−|‒)")
    sice = prog.sub("-", ice)  # hyphen-minus
    seng = prog.sub("-", eng)  # hyphen-minus
    return {"is": sice, "en": seng}


@register_transformation
def soft_hyphen(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(SUBSTITUTE_FOR_NULL)
    return {"is": prog.sub("", ice), "en": prog.sub("", eng)}


@register_transformation
def merge_spaces(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(r"\s+")
    ice = prog.sub(" ", ice).strip(" ")
    eng = prog.sub(" ", eng).strip(" ")
    return {"is": ice, "en": eng}


@register_filter
def deduplicate(ex):
    return Deduplifier.is_unique_example(ex)


@register_filter
def banned_symbol(ex):
    # TODO(haukurb): this filter is to gather file ids for filtering
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(BANNED_SYMBOLS_PAT)
    backslash = "\\"
    found = backslash in ice
    found = found or backslash in eng
    found = found or prog.search(ice) or prog.search(eng)
    return not found


@register_filter
def whitelist_symbol(ex):
    ice, eng = ex["is"], ex["en"]
    chars_ex = set(ice)
    chars_ex.update(eng)
    has_non_whitelisted = bool(chars_ex - SYMBOL_WHITELIST)
    return not has_non_whitelisted


@register_filter
def null_sentence(ex):
    prog = RegexCache.compile_rx(r"^\s+$")
    is_only_spaces = prog.match(ex["is"]) or prog.match(ex["en"])
    is_empty = not ex["is"] or not ex["en"]
    return not is_only_spaces and not is_empty


@register_filter
def quote_inside_word(ex):
    # TODO(haukurb): gather file ids from this filter
    prog = RegexCache.compile_rx(r'\w+"\w')
    has_error = prog.search(ex["is"]) or prog.search(ex["en"])
    return not has_error


@register_filter
def ocr_wrong_symbol(ex):
    # TODO(haukurb): gather file ids from this filter
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(r",,")
    return not prog.search(ice)


@register_filter
def ocr_word_boundary_avg_length(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(r"\w+")
    lens_ice = [len(m) for m in prog.findall(ice)]
    lens_eng = [len(m) for m in prog.findall(eng)]
    avg_ice = sum(lens_ice) / len(lens_ice)
    avg_eng = sum(lens_eng) / len(lens_eng)
    return avg_ice > 1.8 and avg_eng > 1.8


@register_filter
def missing_letter(ex):
    # TODO(haukurb): gather file ids from this filter
    ice = ex["is"]
    substrings = [
        r" a ",
        r" e ",
        r" i ",
        r" o ",
        r" u ",
        r" y ",
        r"\bvi\b",
        r"\bess\b",
        r"\bme\b",
        r"\bessum\b",
    ]
    found = re.search("(" + "|".join(substrings) + ")", ice)
    return not found


@register_filter
def alphanumeric(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(r"[^\d\W]")
    mice = prog.search(ice)
    meng = prog.search(eng)
    return mice and meng


@register_filter
def sentence_length_ratio(ex):
    ice, eng = len(ex["is"]), len(ex["en"])
    res1 = ice > 3 or not (ice < 3 * eng)  # ice > 3 implies ice < 3 * eng
    res2 = eng > 3 or not (eng < 3 * ice)
    return res1 and res2


@register_filter
def strict_sentence_length_ratio(ex):
    ice, eng = len(ex["is"]), len(ex["en"])
    res1 = ice > 3 or not (ice < 2 * eng)  # ice > 3 implies ice < 3 * eng
    res2 = eng > 3 or not (eng < 2 * ice)
    return res1 and res2


@register_filter
def token_count_ratio(ex):
    if not T2T_AVAILABLE:
        print(
            "Skipping {0} because t2t is not available".format(
                token_count_ratio.__name__
            ),
            file=sys.stderr,
        )
        return ex
    enc = get_or_initialize_encoder()
    ice = len(enc.encode(ex["is"]))
    eng = len(enc.encode(ex["en"]))
    # ice > n implies ice < k * eng is equivalent to
    MIN_COUNT = 4
    if ice < MIN_COUNT or eng < MIN_COUNT:
        return True

    res = (0.5 * ice < eng) and (0.5 * eng < ice)
    return res


@register_filter
def case_mismatch(ex):
    ice, eng = ex["is"], ex["en"]
    ice = ice.upper() == ice
    eng = eng.upper() == eng
    return ice == eng


@register_filter
def digit_mismatch(ex):
    prog = RegexCache.compile_rx(r"\D+")
    # Remove non-digit characters, group consecutive numbers, filter empty string
    ice = [w for w in prog.sub(" ", ex["is"]).strip(" ").split(" ") if w]
    eng = [w for w in prog.sub(" ", ex["en"]).strip(" ").split(" ") if w]
    dice = collections.Counter(ice)
    deng = collections.Counter(eng)
    mismatch = bool(dice - deng) or bool(deng - dice)
    return not mismatch


@register_filter
def quote_mismatch(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx(re.escape('"'))
    nice = len(prog.findall(ice))
    neng = len(prog.findall(eng))
    return nice % 2 == 0 or neng % 2 == 0


@register_filter
def abs_min_string_edit(ex):
    ice, eng = ex["is"], ex["en"]
    dist = editdistance.eval(ice, eng)
    return dist >= 3


@register_filter
def rel_min_string_edit(ex):
    ice, eng = ex["is"], ex["en"]
    num_edits = editdistance.eval(ice, eng)
    lengths = [len(ice), len(eng)]
    min_ratio = num_edits / min(lengths)
    max_ratio = num_edits / max(lengths)
    return (max_ratio >= 0.10) and (min_ratio >= 0.10)


@register_filter
def abs_min_subtoken_edit(ex):
    enc = get_or_initialize_encoder()
    ice = enc.encode(ex["is"])
    eng = enc.encode(ex["en"])
    dist = editdistance.eval(ice, eng)
    return dist >= 2


@register_filter
def rel_min_subtoken_edit(ex):
    enc = get_or_initialize_encoder()
    ice = enc.encode(ex["is"])
    eng = enc.encode(ex["en"])
    num_edits = editdistance.eval(ice, eng)
    lengths = [len(ice), len(eng)]
    min_ratio = num_edits / min(lengths)
    max_ratio = num_edits / max(lengths)
    return (max_ratio >= 0.10) and (min_ratio >= 0.10)


@register_filter
def colon_mismatch(ex):
    ice, eng = ex["is"], ex["en"]
    mismatch = ":" in ice and (":" not in eng and ";" not in eng)
    mismatch = mismatch or (":" in eng and ":" not in ice)
    return not mismatch


@register_filter
def corrupt_symbol(ex):
    ice, eng = ex["is"], ex["en"]
    symbols = re.escape("?")
    pat = r"\w[" + symbols + "]+\w"
    prog = RegexCache.compile_rx(pat)
    found = prog.search(ice) or prog.search(eng)
    return not found


@register_filter
def improper_line_split(ex):
    ice, eng = ex["is"], ex["en"]
    ice_prog = RegexCache.compile_rx(r"(\b(?!\d)\w+)- (\b(?!eða|og)\w+\b)")
    ice_matches = ice_prog.findall(ice)
    eng_prog = RegexCache.compile_rx(r"(\b(?!\d)\w+- \b(?!or|and)\w+\b)")
    eng_matches = eng_prog.findall(eng)
    return len(ice_matches) == 0 or len(eng_matches) == 0


@register_filter
def dot_pattern(ex):
    ice, eng = ex["is"], ex["en"]
    prog = RegexCache.compile_rx("(" + r"\.\s+" + "){2,}")
    found = prog.search(ice) or prog.search(eng)
    return not found


@register_filter
def bullet_mismatch(ex):
    # Suggests misalignment since a bullet is a sentence boundary
    ice, eng = ex["is"], ex["en"]
    nice = ice.count("•")
    neng = eng.count("•")
    return nice == neng


@register_filter
def max_word_length(ex):
    ice, eng = ex["is"], ex["en"]
    word_prog = RegexCache.compile_rx(r"\b\w+\b")
    ice_words = word_prog.findall(ice)
    eng_words = word_prog.findall(eng)
    max_ice_len = 50
    max_eng_len = 50
    return (
        max(len(w) for w in ice_words) <= max_ice_len
        and max(len(w) for w in eng_words) <= max_eng_len
    )


@register_filter
def min_word_count(ex):
    isl_toks = [
        tok
        for tok in tokenizer.tokenize(ex["is"])
        if tok.txt is not None and tok.kind == tokenizer.TOK.WORD
    ]
    eng_toks = [
        tok
        for tok in tokenizer.tokenize(ex["en"])
        if tok.txt is not None and tok.kind == tokenizer.TOK.WORD
    ]
    return (
        len(isl_toks) >= DEFAULT_MIN_WORD_COUNT
        and len(eng_toks) >= DEFAULT_MIN_WORD_COUNT
    )


class Gather:

    _store = None
    _prev_store = None
    _initialized_with_file = False

    @classmethod
    def _idemp_init(cls):
        """ Idempotently initialize, if gather data exists from last run
            it will be used to filter/transform. Otherwise, pipeline needs
            to be executed twice. """
        raise NotImplementedError

    @classmethod
    def gather(cls, ex):
        raise NotImplementedError

    @classmethod
    def save_to_file(cls):
        # Write gathered data to file
        # This depends on the data structure the gatherer uses
        raise NotImplementedError


class MinFrequency(Gather):

    auto_pass_len = 3  # for numbers and abbreviations
    min_freq = 2
    word_prog = RegexCache.compile_rx(r"\b\w+\b")
    num_prog = RegexCache.compile_rx(r"^\d+$")

    @classmethod
    def _idemp_init(cls):
        if cls._store is not None:
            return
        try:
            os.makedirs(_TMP_DIR, exist_ok=True)
            path = os.path.join(_TMP_DIR, cls.__name__)
            with open(path, "r") as fh:
                cls._prev_store = json.load(fh)
        except (FileNotFoundError, json.decoder.JSONDecodeError) as e:
            pass
        cls._store = {"eng": collections.Counter(), "ice": collections.Counter()}

    @classmethod
    def save_to_file(cls):
        try:
            os.makedirs(_TMP_DIR, exist_ok=True)
            path = os.path.join(_TMP_DIR, cls.__name__)
            with open(path, "w") as fh:
                json.dump(cls._store, fh, indent=2)
        except FileNotFoundError:
            pass

    @classmethod
    def gather(cls, ex):
        cls._idemp_init()
        ice, eng = ex["is"], ex["en"]
        ice_words = cls.word_prog.findall(ice)
        eng_words = cls.word_prog.findall(eng)
        ice_words = [
            w.lower()
            for w in ice_words
            if len(w) > cls.auto_pass_len and not cls.num_prog.match(w)
        ]
        eng_words = [
            w.lower()
            for w in eng_words
            if len(w) > cls.auto_pass_len and not cls.num_prog.match(w)
        ]
        cls._store["ice"].update(ice_words)
        cls._store["eng"].update(eng_words)

        if cls._prev_store:
            pice = all(
                cls._prev_store["ice"].get(w, 0) >= cls.min_freq for w in ice_words
            )
            peng = all(
                cls._prev_store["eng"].get(w, 0) >= cls.min_freq for w in eng_words
            )
            return pice and peng
        return True


@register_filter
def wrong_quotes(ex):
    ice, eng = ex["is"], ex["en"]

    QUOTES = set(QUOTE_LIKE)
    QUOTES.remove("'")
    QUOTES.remove('"')
    QUOTES.remove(",")
    for q in ICE_QUOTE.ALL:
        try:
            QUOTES.remove(q)
        except:
            pass

    chars_ex = set(ice)
    chars_ex.update(eng)

    return not bool(chars_ex & QUOTES)


# @register_filter
# def language(ex):
#     ice, eng = ex["is"], ex["en"]
#     correct = probably_correct_language(ice, "is", lower_bound=0.995)
#     correct = correct and probably_correct_language(eng, "en", lower_bound=0.995)
#     return correct


class Pipeline:

    counter = dict()
    _fns = [
        ### filters
        null_sentence,
        alphanumeric,
        banned_symbol,
        whitelist_symbol,
        digit_mismatch,
        deduplicate,
        case_mismatch,
        max_word_length,
        min_word_count,
        ### transformations
        fix_improper_line_split,
        remove_leading_bullet,
        soft_hyphen,
        replace_dashes,
        merge_spaces,
        fix_ice_quotes,
        ### filters
        bullet_mismatch,
        quote_mismatch,
        ocr_wrong_symbol,
        colon_mismatch,
        missing_letter,
        corrupt_symbol,
        quote_inside_word,
        abs_min_string_edit,
        rel_min_string_edit,
        abs_min_subtoken_edit,
        rel_min_subtoken_edit,
        sentence_length_ratio,
        strict_sentence_length_ratio,
        token_count_ratio,
        ocr_word_boundary_avg_length,
        dot_pattern,
        wrong_quotes,
        # language,
        # MinFrequency.gather,
        # MinFrequency,
        # MostCommon50k,
    ]
    start_time = None
    end_time = None

    @classmethod
    def run(cls, examples, view_function=None, inverted=False, **kwargs):
        cls.start_time = time.time()
        cls.counter.clear()
        cls.counter["total"] = 0
        for ex in examples:
            cls.counter["total"] += 1
            ex = cls.process(ex, view_function=view_function, inverted=inverted)
            if ex is not None:
                yield ex

        for obj in cls._fns:
            if not isinstance(obj, type):
                continue
            obj.save_to_file()
        cls.end_time = time.time()

    @classmethod
    def process(cls, ex, view_function=None, inverted=False):
        for obj in cls._fns:
            fn = obj.gather if isinstance(obj, type) else obj
            name = obj.__name__ if isinstance(obj, type) else fn.__name__
            display = view_function == name
            if name in Transformations._transforms:
                old = dict(ex)
                ex = obj(ex)
                if ex != old:
                    out_ex = old if inverted else ex
                    if display:
                        print_ex(out_ex)
                    cls.counter[name] = cls.counter.get(name, 0) + 1
            else:
                if display and inverted:
                    print_ex(ex)
                if not fn(ex):
                    cls.counter[name] = cls.counter.get(name, 0) + 1
                    if display and not inverted:
                        print_ex(ex)
                    return None

        return ex

    @classmethod
    def summarize_counter(cls, indent=4, file=sys.stdout):
        total = cls.counter["total"]
        cls.counter.pop("total")
        num_filtered = sum(
            count
            for name, count in cls.counter.items()
            if name not in Transformations._transforms
        )
        num_transformed = sum(
            count
            for name, count in cls.counter.items()
            if name in Transformations._transforms
        )
        print(
            "Examples remaining:  {rem:>8d} / {total:<8d}  {pct:5.2f}%  in {elaps:>5.1f} seconds".format(
                rem=total - num_filtered,
                total=total,
                pct=100 * (total - num_filtered) / (total or 1),
                elaps=cls.end_time - cls.start_time,
            )
        )
        print("-" * 80)
        print(
            "{indent}{name:<30s}  {count:>8s}   {pct:>5s}  {rel:<10s}".format(
                indent=" " * indent,
                name="Name",
                count="Count",
                pct="Total",
                rel="Total filtered",
            )
        )
        for fn in cls._fns:
            name = fn.__name__
            if name not in cls.counter:
                continue
            count = cls.counter[name]

            filter_msg = "{indent}{name:<30s}  {count:>8d}  {pct:>5.2f}%  {rel:>13.2f}%".format(
                indent=" " * indent,
                name=name,
                count=count,
                pct=100 * count / (total or 1),
                rel=100 * count / (num_filtered or 1),
            )

            transform_msg = "{indent}{name:<30s}  {count:>8d}  {pct:>5.2f}%".format(
                indent=" " * indent,
                name=name,
                count=count,
                pct=100 * count / (total or 1),
            )
            msg = filter_msg if name in Filters._filters else transform_msg
            print(msg)


class MinimalPipeline(Pipeline):

    counter = dict()
    _fns = [
        ### filters
        null_sentence,
        alphanumeric,
        whitelist_symbol,
        digit_mismatch,
        deduplicate,
        case_mismatch,
        max_word_length,
        #min_word_count,
        ### transformations
        fix_improper_line_split,
        #remove_leading_bullet,
        soft_hyphen,
        replace_dashes,
        merge_spaces,
        fix_ice_quotes,
        wrong_quotes,
        ### filters
        bullet_mismatch,
        quote_mismatch,
        ocr_wrong_symbol,
        colon_mismatch,
        missing_letter,
        corrupt_symbol,
        quote_inside_word,
        ocr_word_boundary_avg_length,
    ]

    start_time = None
    end_time = None


def do_pipeline(
    in_file=None,
    out_file=sys.stdout,
    quiet=False,
    summary=False,
    view_function=None,
    inverted=False,
    **kwargs
):
    examples = lines_to_examples(in_file)
    pipeline = MinimalPipeline
    for ex in pipeline.run(examples, view_function=view_function, inverted=inverted):
        if not quiet and view_function is None:
            print("\t".join([ex["en"], ex["is"]]), file=out_file)
    if summary:
        pipeline.summarize_counter()


def lines_to_examples(lines):
    for line in lines:
        line = line.strip("\n")
        src, tgt = line.split("\t")[:2]
        ex = {"en": src, "is": tgt}
        yield ex


class TransformationPipeline(Pipeline):
    _fns = [
        fix_improper_line_split,
        remove_leading_bullet,
        soft_hyphen,
        replace_dashes,
        merge_spaces,
        fix_ice_quotes,
    ]


def do_fns(
    in_file=None, transforms=[], filters=[], quiet=False, use_pipeline=False, **kwargs
):
    for ex in lines_to_examples(in_file):
        for transform in transforms:
            ex = Transformations.apply(transform, ex)
        for filter_name in filters:
            inverted = False
            if filter_name.endswith("_inv"):
                inverted = True
                filter_name = filter_name.strip("_inv")
            if Filters.apply(filter_name, ex, inverted=inverted):
                if not quiet:
                    print("\t".join([ex["en"], ex["is"]]))


def valid_view_function(string):
    import argparse

    if string in [fn.__name__ for fn in Pipeline._fns]:
        return string
    raise argparse.ArgumentError("Invalid filter/transformation name")


if __name__ == "__main__":

    try:
        import argcomplete
    except ImportError as exc:
        pass
    import argparse

    parser = argparse.ArgumentParser(
        "Filters and transformation pipelines for monolingual and parallel corpora. "
        "Input defaults to stdin (with tab delimiter) if no input file is supplied."
    )

    parser.add_argument(
        "-i",
        "--in_file",
        dest="in_file",
        type=argparse.FileType("r"),
        default=sys.stdin,
        required=0,
        help="Sample file to run filter through, defaults to stdin",
    )
    parser.add_argument(
        "-f",
        "--filters",
        dest="filters",
        type=str,
        required=False,
        default=[],
        nargs="+",
        help="Filters to run sample through.",
    )
    parser.add_argument(
        "-t",
        "--transforms",
        dest="transforms",
        type=str,
        required=False,
        default=[],
        nargs="+",
        help="Transforms to run sample through.",
    )
    parser.add_argument(
        "-q",
        "--no_examples",
        dest="quiet",
        required=False,
        default=False,
        action="store_true",
        help="Do not output lines after transformations and filtering (for summary statistics).",
    )
    parser.add_argument(
        "-s",
        "--summary",
        dest="summary",
        action="store_true",
        required=False,
        default=False,
        help="Help",
    )
    parser.add_argument(
        "--hook",
        dest="view_function",
        type=valid_view_function,
        required=False,
        default=None,
        help="Display filter or transformation output as occurs in the pipeline.",
    )
    parser.add_argument(
        "-v",
        "--invert",
        dest="inverted",
        action="store_true",
        required=False,
        default=False,
        help=(
            "Print inverse of filter as it occurs in the pipeline"
            "(or the output that is unaffected by a hooked transformation)."
        ),
    )
    parser.add_argument(
        "-o",
        "--out_file",
        dest="out_file",
        type=argparse.FileType("w"),
        required=False,
        default=sys.stdout,
        help="File where pipline output will be written",
    )

    # TODO: define pipeline via config file

    args = parser.parse_args()
    if args.filters or args.transforms:
        do_fns(**vars(args))
    else:
        do_pipeline(**vars(args))
