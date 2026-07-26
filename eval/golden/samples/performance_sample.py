"""Sample file with intentional performance issues for eval/golden performance dataset."""


def find_duplicates(items):
    # Perf: O(n^2) nested loop to find duplicates instead of using a set.
    duplicates = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j] and items[i] not in duplicates:
                duplicates.append(items[i])
    return duplicates


def build_report(rows):
    # Perf: string concatenation in a loop is O(n^2); should use "".join(...).
    report = ""
    for row in rows:
        report += str(row) + "\n"
    return report


def contains_any(haystack, needles):
    # Perf: `in` on a list is O(n) per check, called in a loop -> O(n*m).
    found = []
    for needle in needles:
        if needle in haystack:
            found.append(needle)
    return found


def load_all_configs(paths):
    # Perf: re-opens and re-parses the same file on every iteration instead of caching.
    results = []
    for path in paths:
        with open(path) as f:
            results.append(f.read())
    return results
