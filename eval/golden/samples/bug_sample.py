"""Sample file with intentional bugs for eval/golden bug_detection dataset."""


def get_first_item(items):
    # Bug: IndexError when items is empty, no guard.
    return items[0]


def average(values):
    # Bug: ZeroDivisionError when values is empty.
    total = sum(values)
    return total / len(values)


def append_to_list(item, bucket=[]):
    # Bug: mutable default argument shared across calls.
    bucket.append(item)
    return bucket


def read_config(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        # Bug: bare except swallows every error, including KeyboardInterrupt/typos.
        pass


def get_user_role(user):
    # Bug: uses `is` for value comparison instead of `==`.
    if user.role is "admin":
        return "administrator"
    return "guest"
