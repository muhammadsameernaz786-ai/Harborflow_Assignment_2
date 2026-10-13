"""Sanitization, sliding-window sequences and cached incident search."""

import json
import re
import data_access as da


def sanitize_report(report):
    result = re.sub(
        r"(?<!\w)[a-z]{4}\d{7}(?!\w)",
        "[CONTAINER]",
        report,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"(?<!\w)SEAL-\d{6}(?!\w)",
        "[SEAL]",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}",
        "[EMAIL]",
        result,
        flags=re.IGNORECASE,
    )
    return result, result != report


def longest_stable_sequence(events):
    start = 0
    best_start = 0
    best_length = 0
    positions = {}

    for end, event in enumerate(events):
        if event in positions and positions[event] >= start:
            start = positions[event] + 1

        positions[event] = end
        length = end - start + 1

        # Using > keeps the first sequence when lengths tie.
        if length > best_length:
            best_start = start
            best_length = length

    return events[best_start:best_start + best_length]


def normalize_words(text):
    return re.sub(r"[^\w\s]|_", " ", text.lower()).split()


def build_index(incidents):
    index = {}
    titles = {}

    for incident in incidents:
        identifier = incident["incident_id"]
        titles[identifier] = incident["title"]

        for word in set(normalize_words(incident["report"])):
            index.setdefault(word, set()).add(identifier)

    return {
        "index": {
            word: sorted(index[word])
            for word in sorted(index)
        },
        "titles": {
            identifier: titles[identifier]
            for identifier in sorted(titles)
        },
    }


def valid_index(value):
    if not isinstance(value, dict) or set(value) != {
        "index", "titles"
    }:
        return False

    index = value["index"]
    titles = value["titles"]

    if not isinstance(index, dict) or not isinstance(titles, dict):
        return False

    if any(
        not isinstance(identifier, str)
        or not isinstance(title, str)
        for identifier, title in titles.items()
    ):
        return False

    for word, identifiers in index.items():
        if (
            not isinstance(word, str)
            or normalize_words(word) != [word]
            or not isinstance(identifiers, list)
        ):
            return False

        if any(
            not isinstance(identifier, str)
            or identifier not in titles
            for identifier in identifiers
        ):
            return False

        if identifiers != sorted(set(identifiers)):
            return False

    return (
        list(index) == sorted(index)
        and list(titles) == sorted(titles)
    )


def load_incident_index(report=print):
    path = da.DATASET / "incident-index.json"
    directory = da.DATASET / "incidents"

    if not directory.is_dir():
        raise FileNotFoundError(
            "Incident source directory unavailable."
        )

    source_paths = da.json_paths(directory, report)

    try:
        cache_time = path.stat().st_mtime_ns
        stale = any(
            source.stat().st_mtime_ns > cache_time
            for source in source_paths
        )

        cached = da.load_json(path)

        if not stale and valid_index(cached):
            return cached

    except (OSError, UnicodeError, json.JSONDecodeError):
        # Missing or unreadable cache: rebuild from source records.
        pass

    incidents, _ = da.load_records(
        directory, "incidents", report
    )
    value = build_index(incidents)
    da.write_json(path, value)
    return value


def search_index(cache, query):
    scores = {}

    for word in set(normalize_words(query)):
        for identifier in cache["index"].get(word, []):
            scores[identifier] = scores.get(identifier, 0) + 1

    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )

    return [
        (identifier, score, cache["titles"][identifier])
        for identifier, score in ranked
    ]
