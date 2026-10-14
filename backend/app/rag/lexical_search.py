"""
Lexical search layer for Hybrid Search.

This module performs keyword-based search over document chunks.
It uses a lightweight BM25 implementation and does not require
an external search engine such as Elasticsearch.
"""

from collections import defaultdict
from contextlib import nullcontext
from typing import Any, Dict, List
import math
import re

from app.rag.trace import active_trace, clip


def normalize_text(text: str) -> str:
    """
    Normalize Persian and Arabic characters
    to make lexical matching more reliable.
    """

    # Arabic Yeh -> Persian Yeh
    text = text.replace("ي", "ی")

    # Arabic Kaf -> Persian Kaf
    text = text.replace("ك", "ک")

    # Arabic Alef Maksura -> Persian Yeh
    text = text.replace("ى", "ی")

    # Remove Persian half-space
    text = text.replace("\u200c", " ")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    # Case-insensitive search
    text = text.lower()

    return text.strip()


def tokenize(text: str) -> List[str]:
    """
    Convert text into searchable tokens.

    Persian words, English words, numbers and codes
    are preserved, minus Persian function-word stopwords (they carry no
    discriminative weight and pollute BM25's IDF). The same filter applies
    at index time and query time, so both sides stay symmetric.
    """

    text = normalize_text(text)

    tokens = re.findall(
        r"[\w\u0600-\u06FF]+",
        text,
        flags=re.UNICODE,
    )
    return [t for t in tokens if t not in PERSIAN_STOPWORDS]


# Persian/Arabic function words only - never content words. Kept literal and
# auditable on purpose (see docs/improvement-workflow.md §3).
PERSIAN_STOPWORDS = frozenset({
    "و", "در", "به", "از", "که", "این", "را", "با", "برای", "تا",
    "است", "هست", "بر", "آن", "های", "ها", "می", "هر", "یا", "هم",
    "یک", "شد", "شده", "خود", "کند", "کنید", "بود", "باشد", "نیز",
    "اما", "همه", "چه", "اگر", "بین", "روی", "درباره", "برای",
})


class LexicalIndex:
    """
    Lightweight in-memory BM25 index.

    The index is rebuilt from the chunks stored in ChromaDB.
    """

    def __init__(self, documents: List[Dict[str, Any]] | None = None,):
        # Store all indexed chunks
        self.documents: List[Dict[str, Any]] = []

        # Term frequencies for every chunk
        self.term_frequencies: List[Dict[str, int]] = []

        # Number of chunks containing each term
        self.document_frequencies: Dict[str, int] = (
            defaultdict(int)
        )

        # Average number of tokens per chunk
        self.average_document_length = 0.0

        if documents:
            self.build(documents)

    def build(self, documents: List[Dict[str, Any]],) -> None:
        """
        Build the lexical index from document chunks.
        """

        # Save the chunks
        self.documents = list(documents)

        # Reset old index data
        self.term_frequencies = []

        self.document_frequencies = defaultdict(int)

        total_length = 0

        # Process every chunk
        for document in self.documents:

            # Get chunk content
            content = document.get(
                "content",
                "",
            )

            # Convert content to tokens
            tokens = tokenize(content)

            # Add its length to the total
            total_length += len(tokens)

            # Count each token in this chunk
            term_frequency = defaultdict(int)

            for token in tokens:
                term_frequency[token] += 1

            # Save term frequencies
            self.term_frequencies.append(
                dict(term_frequency)
            )

            # Count how many chunks contain each token
            for token in term_frequency:
                self.document_frequencies[token] += 1

        # Calculate average chunk length
        if self.documents:
            self.average_document_length = (
                total_length / len(self.documents)
            )
        else:
            self.average_document_length = 0.0

    def search(
        self,
        query: str,
        top_k: int = 8,
        k1: float = 1.5,
        b: float = 0.75,
        label: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Search the index using BM25 scoring.

        ``label`` only tags the recorded trace stage (see app.rag.trace); the
        ranking is unaffected. When a trace is recording, the BM25 internals
        that decide the ranking - tokenisation, per-term IDF, k1/b and the
        length normalisation of each hit - are stored for the viewer.

        The stage wraps the whole call - tokenisation, IDF, scoring, sorting
        and row assembly - so its ``ms`` is the real cost of the search. The
        expensive parts are all after tokenisation, and timing only the first
        step reported a search that had already finished as free.
        """

        trace = active_trace()
        context = (
            trace.stage((f"{label}" if label else "") + "lexical_search",
                        "جست‌وجوی واژگانی (BM25)")
            if trace is not None else nullcontext({})
        )
        with context as stage:
            # Convert query into tokens
            query_tokens = tokenize(query)

            if stage:
                stage["command"] = (
                    "score = Σ idf(term) · tf · (k1+1) / (tf + k1·(1 - b + b·dl/avgdl))"
                )
                stage["meta"] = {
                    "indexed_chunks": len(self.documents),
                    "query": clip(query, 200),
                    "query_tokens": query_tokens[:40],
                    "k1": k1,
                    "b": b,
                    "average_chunk_tokens": round(self.average_document_length, 1),
                    "candidates_requested": top_k,
                    "timed": "کل جست‌وجو (توکن‌سازی، IDF، امتیازدهی، مرتب‌سازی)",
                }

            # Nothing to search
            if not query_tokens:
                if stage:
                    stage["meta"]["stopped"] = "هیچ توکنی از پرسش استخراج نشد"
                return []

            # Number of chunks
            document_count = len(
                self.documents
            )

            if document_count == 0:
                if stage:
                    stage["meta"]["stopped"] = "ایندکس واژگانی خالی است (هیچ تکه‌ای برای این کاربر فهرست نشده)"
                return []

            # Precompute the BM25 IDF per unique query term once (it depends
            # only on the corpus, not on the chunk), then score each chunk that
            # actually contains at least one query term. Scanning the postings
            # instead of every chunk keeps this O(matching chunks x terms)
            # instead of O(chunks x terms).
            term_idf: Dict[str, float] = {}
            for term in set(query_tokens):
                document_frequency = self.document_frequencies.get(term, 0)
                if document_frequency == 0:
                    continue
                term_idf[term] = math.log(
                    1
                    + (
                        document_count
                        - document_frequency
                        + 0.5
                    )
                    / (
                        document_frequency
                        + 0.5
                    )
                )

            if stage:
                stage["meta"]["term_idf"] = {term: round(idf, 4) for term, idf in term_idf.items()}
                stage["meta"]["terms_not_in_corpus"] = sorted(set(query_tokens) - set(term_idf))[:20]

            avg_dl = max(self.average_document_length, 1)
            matching = []
            for index, term_frequency in enumerate(self.term_frequencies):
                score = 0.0
                for term, idf in term_idf.items():
                    frequency = term_frequency.get(term, 0)
                    if frequency == 0:
                        continue
                    score += (
                        idf
                        * frequency
                        * (k1 + 1)
                        / (
                            frequency
                            + k1
                            * (
                                1
                                - b
                                + b
                                * (sum(term_frequency.values()) or 1)
                                / avg_dl
                            )
                        )
                    )
                if score > 0:
                    matching.append((index, score))

            # Rank only the chunks with a positive score (same ranking as before,
            # computed without touching zero-score chunks).
            matching.sort(key=lambda pair: pair[1], reverse=True)
            results = []
            rows = []
            for rank, (index, score) in enumerate(matching[:top_k], start=1):
                result = dict(self.documents[index])
                result["lexical_score"] = round(score, 4)
                results.append(result)
                if stage:
                    term_frequency = self.term_frequencies[index]
                    rows.append({
                        "rank": rank,
                    "id": str(result.get("id") or ""),
                        "doc": str(result.get("document_name") or ""),
                        "chunk": result.get("chunk_index", ""),
                        "score": round(score, 4),
                        "terms": "، ".join(sorted(t for t in term_idf if term_frequency.get(t)))[:80],
                        "preview": clip(result.get("content") or ""),
                    })
            if stage:
                stage["columns"] = [
                    {"key": "rank", "label": "رتبه"},
                    {"key": "id", "label": "شناسه تکه"},
                    {"key": "doc", "label": "سند"},
                    {"key": "chunk", "label": "تکه"},
                    {"key": "score", "label": "امتیاز BM25"},
                    {"key": "terms", "label": "کلیدواژه‌های منطبق"},
                    {"key": "preview", "label": "متن تکه"},
                ]
                stage["rows"] = rows
                stage["meta"]["scored_chunks"] = len(matching)
                stage["meta"]["hits"] = len(results)
            return results
