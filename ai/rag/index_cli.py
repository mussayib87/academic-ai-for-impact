import json

from ai.rag.index import index_documents


def main() -> None:
    print(json.dumps(index_documents(), indent=2))


if __name__ == '__main__':
    main()