import time


def print_timing(func):
    """A simple decorator to print the length of time a function takes to
    complete.
    """
    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        print 'Completed in %0.1f seconds' % ((t2 - t1))
        return res
    return wrapper
