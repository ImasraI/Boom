"""Open Chroma collections without replacing their stored provenance."""


def get_or_create_collection(client, name, *, metadata):
    # Chroma 0.5.5 replaces existing metadata when get_or_create receives it.
    # Supply defaults only when creating a collection, never while opening it.
    try:
        return client.get_collection(name, embedding_function=None)
    except ValueError:
        return client.get_or_create_collection(name, embedding_function=None, metadata=metadata)
