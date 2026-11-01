"""Private, model/task-bound query-vector cache for repeatable local evaluations."""
import hashlib
import math
from pathlib import Path
from app.rag.exam_corpus import atomic_json, read_json


class EvaluationCache:
    def __init__(self, path, model, dimensions):
        self.path = Path(path)
        self.model = model
        self.dimensions = dimensions
        saved = read_json(self.path, {})
        self.entries = saved if isinstance(saved, dict) else {}

    def key(self, text, task):
        return hashlib.sha256(f'{self.model}\0{self.dimensions}\0{task}\0{text}'.encode()).hexdigest()

    def valid(self, vector):
        return (isinstance(vector, list) and len(vector) == self.dimensions
                and all(type(v) in (int, float) and math.isfinite(v) for v in vector)
                and any(v != 0 for v in vector))

    def get(self, text, task):
        vector = self.entries.get(self.key(text, task))
        return vector if self.valid(vector) else None

    def put(self, text, task, vector):
        if not self.valid(vector):
            raise ValueError('Invalid evaluation embedding')
        self.entries[self.key(text, task)] = vector
        atomic_json(self.path, self.entries)
