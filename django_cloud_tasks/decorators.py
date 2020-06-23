import logging

from functools import wraps, partial

from .base import BaseTask, CloudTaskWrapper
from .registries import registry


logger = logging.getLogger(__name__)


def _gen_internal_task_name(task_func):
    internal_task_name = '.'.join((task_func.__module__, task_func.__name__))
    return internal_task_name


def log_execution(task_name, retry_count_before_error=5):
    """
    Decorator to make a task verbose during execution.
    """

    def decorator(func):
        def inner_run(request, *task_args, **task_kwargs):

            retry_count = int(
                request.request_headers.get("HTTP_X_APPENGINE_TASKRETRYCOUNT", 0)
            )

            logger.info(
                "Asynchronous task {}: starting execution (task_id={}, "
                "current retry_count={}).".format(
                    task_name, request.task_id, retry_count
                )
            )
            exception = None
            try:
                func(request, *task_args, **task_kwargs)
            except Exception as e:
                exception = e
                raise e
            finally:
                if exception is None:
                    logger.info(
                        "Asynchronous task {}: executed with success "
                        "(task_id={}, current retry_count={}).".format(
                            task_name, request.task_id, retry_count
                        )
                    )
                else:
                    error = "{}: {}".format(exception.__class__.__name__, exception)

                    if retry_count > retry_count_before_error:
                        logger.exception(
                            "Asynchronous task {}: after many attempts, failed to "
                            "execute it properly (task_id={}, current retry_count={}, "
                            "error={}).".format(
                                task_name, request.task_id, retry_count, error
                            )
                        )
                    else:
                        logger.warning(
                            "Asynchronous task {}: in failure (task_id={}, current "
                            "retry_count={}, error={}).".format(
                                task_name, request.task_id, retry_count, error
                            )
                        )

        return inner_run

    return decorator


def create_task(task_class, func, **kwargs):

    internal_task_name = _gen_internal_task_name(func)

    run = partial(log_execution(task_name=internal_task_name)(func))

    attrs = {
        'internal_task_name': internal_task_name,
        'run': run,
        '__module__': func.__module__,
        '__doc__': func.__doc__}
    attrs.update(kwargs)

    return type(func.__name__, (task_class,), attrs)()


def task(queue, **headers):
    def decorator(func):
        task_cls = create_task(BaseTask, func)
        registry.register(task_cls)

        @wraps(func)
        def inner_run(**kwargs):
            return CloudTaskWrapper(task_cls, queue, kwargs, headers=headers)

        return inner_run

    return decorator
