import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufffe\ufeff]")


def sanitize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value)
    text = ZERO_WIDTH_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def load_data(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_documents(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Check if data is already in document format (has 'url' and 'section_title' fields)
    if data and all(key in data[0] for key in ['url', 'section_title']):
        # Already processed, return as-is
        return data
    
    # Otherwise, process raw Scrapy format
    documents: List[Dict[str, Any]] = []
    for page in data:
        page_url = page.get("url")
        page_title = sanitize_text(page.get("title"))
        page_meta = sanitize_text(page.get("meta_description", ""))
        for section in page.get("sections", []):
            documents.append({
                "url": page_url,
                "page_title": page_title,
                "meta_description": page_meta,
                "section_title": sanitize_text(section.get("section_title")),
                "heading_level": section.get("heading_level"),
                "content": sanitize_text(section.get("content", "")),
            })
    return documents


def normalize_query(query: str) -> List[str]:
    query = query.strip().lower()
    if not query:
        return []
    terms = re.findall(r'"([^"]+)"|(\S+)', query)
    results: List[str] = []
    for quoted, token in terms:
        value = quoted or token
        if value:
            results.append(value.strip())
    return results


def find_matches(document: Dict[str, Any], terms: List[str], fields: List[str], radius: int) -> Optional[Dict[str, Any]]:
    text_fields = []
    for field in fields:
        value = document.get(field, "")
        if value:
            text_fields.append((field, str(value)))

    hits = []
    total_hits = 0
    for term in terms:
        for field_name, value in text_fields:
            count = value.lower().count(term.lower())
            if count:
                hits.append({"term": term, "field": field_name, "count": count})
                total_hits += count

    if total_hits == 0:
        return None

    excerpt_text = build_excerpt(document, terms, radius=radius)
    return {
        "url": document.get("url"),
        "page_title": document.get("page_title"),
        "section_title": document.get("section_title"),
        "heading_level": document.get("heading_level"),
        "meta_description": document.get("meta_description"),
        "content": document.get("content"),
        "matches": hits,
        "score": total_hits,
        "excerpt": excerpt_text,
    }


def build_excerpt(document: Dict[str, Any], terms: List[str], radius: int = 120) -> str:
    content = str(document.get("content", ""))
    lower = content.lower()
    best_index = None
    for term in terms:
        idx = lower.find(term.lower())
        if idx != -1 and (best_index is None or idx < best_index):
            best_index = idx

    if best_index is None:
        return content[: radius * 2].strip()

    start = max(0, best_index - radius)
    end = min(len(content), best_index + len(terms[0]) + radius)
    excerpt = content[start:end].strip()
    excerpt = re.sub(r"\s+", " ", excerpt)
    if start > 0:
        excerpt = "... " + excerpt
    if end < len(content):
        excerpt = excerpt + " ..."
    return excerpt


def search_documents(
    documents: List[Dict[str, Any]],
    query: str,
    fields: List[str],
    max_results: Optional[int] = None,
    radius: int = 120,
) -> List[Dict[str, Any]]:
    terms = normalize_query(query)
    if not terms:
        return []

    results = []
    for document in documents:
        match = find_matches(document, terms, fields, radius=radius)
        if match:
            results.append(match)

    results.sort(key=lambda item: item["score"], reverse=True)
    if max_results:
        return results[:max_results]
    return results


def write_json(path: Path, data: Any, pretty: bool = False) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) if pretty else json.dumps(data, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def write_jsonl(path: Path, data: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Warcry extracted JSON output")
    parser.add_argument("query", help="Search query, e.g. deployment or \"battle plan\"")
    parser.add_argument("--input", "-i", default="warcry_searchable.json", help="input JSON file")
    parser.add_argument("--output", "-o", help="optional output JSON file")
    parser.add_argument("--jsonl", action="store_true", help="write newline-delimited JSON instead of array JSON")
    parser.add_argument("--chat-ready", help="write a ChatGPT-friendly JSONL file with results")
    parser.add_argument("--fields", default="page_title,section_title,content,meta_description", help="comma-separated fields to search")
    parser.add_argument("--max-results", type=int, default=50, help="maximum number of results to return")
    parser.add_argument("--context", type=int, default=120, help="excerpt context radius")
    parser.add_argument("--pretty", action="store_true", help="pretty-print output JSON")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    data = load_data(path)
    documents = build_documents(data)
    fields = [field.strip() for field in args.fields.split(",") if field.strip()]
    results = search_documents(
        documents,
        args.query,
        fields,
        max_results=args.max_results,
        radius=args.context,
    )

    print(f"Found {len(results)} matching sections for query: {args.query}")
    for item in results[: min(10, len(results))]:
        print(f"[{item['score']} hits] {item['url']} | {item['section_title']}")
        print(item["excerpt"])
        print()

    if args.output:
        out_path = Path(args.output)
        if args.jsonl:
            write_jsonl(out_path, results)
        else:
            write_json(out_path, results, pretty=args.pretty)
        print(f"Saved {len(results)} results to {out_path}")

    if args.chat_ready:
        chat_path = Path(args.chat_ready)
        chat_results = [
            {
                "source": item["url"],
                "title": item["page_title"],
                "section": item["section_title"],
                "excerpt": item["excerpt"],
                "content": item["content"],
            }
            for item in results
        ]
        write_jsonl(chat_path, chat_results)
        print(f"Saved {len(chat_results)} chat-ready results to {chat_path}")


if __name__ == "__main__":
    main()
