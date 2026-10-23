import time
from collections.abc import Callable


def print_timing[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """A decorator to print the length of time a function takes to
    complete.
    """

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        t1 = time.time()
        res = func(*args, **kwargs)
        t2 = time.time()
        print(f"Completed in {t2 - t1:0.1f} seconds.")
        return res

    return wrapper
