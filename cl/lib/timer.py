import time


def print_timing(func):
    """A decorator to print the length of time a function takes to
    complete.
    """

    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        print(f"Completed in {t2 - t1:0.1f} seconds.")
        return res

    return wrapper
