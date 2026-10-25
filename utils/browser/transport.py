from contextlib import contextmanager


@contextmanager
def command_timeout(driver, seconds):
    config = driver.command_executor.client_config
    previous = config.timeout
    config.timeout = seconds
    try:
        yield
    finally:
        config.timeout = previous
