from app.intelligence.workers.experiment_worker import process as process_experiment_worker
from app.intelligence.workers.learning_worker import process as process_learning_worker
from app.intelligence.workers.outbox_worker import process as process_outbox_worker


def run_worker(worker_name: str, payload: dict[str, object]) -> dict[str, object]:
    if worker_name == 'learning':
        return process_learning_worker(payload)
    if worker_name == 'experiment':
        return process_experiment_worker(payload)
    if worker_name == 'outbox':
        return process_outbox_worker(payload)
    raise ValueError(f'Unknown intelligence worker: {worker_name}')


__all__ = ['run_worker']
