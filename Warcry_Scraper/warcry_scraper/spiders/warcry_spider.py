import logging
from urllib.parse import urlparse

import scrapy


class WarcrierSpider(scrapy.Spider):
    """Robust crawler for Warcrier docs.

    Features:
    - Normalises and follows only `/docs/` pages on `warcrier.net`.
    - Deduplicates visited URLs.
    - Optional `max_pages` spider argument to limit crawl for testing.
    - Extracts page metadata and structured sections (headings -> content).
    """

    name = "warcrier_full"
    allowed_domains = ["warcrier.net"]
    start_urls = ["https://www.warcrier.net/docs/intro"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visited_urls = set()
        # allow passing -a max_pages=10 to limit crawl for tests
        self.max_pages = int(getattr(self, "max_pages", 0))
        self.visited_count = 0

    def parse(self, response):
        url = response.url
        if url in self.visited_urls:
            return

        if self.max_pages and self.visited_count >= self.max_pages:
            return

        self.visited_urls.add(url)
        self.visited_count += 1

        # Page-level metadata
        item = {
            "url": url,
            "title": response.css("h1::text").get(),
            "meta_description": response.css('meta[name=description]::attr(content)').get(),
            "sections": self.extract_sections(response),
        }

        yield item

        # Follow internal docs links only
        for href in response.css("a::attr(href)").getall():
            norm = self.normalize_href(href, response)
            if not norm:
                continue
            if norm in self.visited_urls:
                continue
            yield response.follow(norm, callback=self.parse)

    def normalize_href(self, href, response):
        """Return an absolute URL to follow, or None if it should be skipped."""
        if not href:
            return None

        href = href.split("#")[0].strip()
        if not href:
            return None

        # Make absolute
        if href.startswith("//"):
            href = response.urljoin(href)
        elif href.startswith("/"):
            href = response.urljoin(href)
        elif href.startswith("http://") or href.startswith("https://"):
            pass
        else:
            # relative path
            href = response.urljoin(href)

        # Only follow docs pages on warcrier.net
        parsed = urlparse(href)
        if "warcrier.net" not in parsed.netloc:
            return None
        if not parsed.path.startswith("/docs/"):
            return None
        return href

    def extract_sections(self, response):
        """Extract sections under heading elements.

        Produces a list of {section_title, heading_level, content}.
        """
        sections = []
        heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

        for header in response.css("h2, h3, h4, h5"):
            title = header.xpath("string(.)").get(default="").strip()
            level = getattr(header.root, "tag", "h").lower()

            content_blocks = []
            for sibling in header.xpath("following-sibling::*"):
                tag = getattr(sibling.root, "tag", "").lower()
                if not tag:
                    continue
                if tag in heading_tags:
                    break
                text = sibling.xpath("string(.)").get(default="").strip()
                if text:
                    content_blocks.append(self.clean_text(text))

            sections.append({
                "section_title": title,
                "heading_level": level,
                "content": "\n\n".join(content_blocks).strip(),
            })

        return sections

    @staticmethod
    def clean_text(text: str) -> str:
        """Normalize whitespace and remove excessive newlines."""
        return " ".join(line.strip() for line in text.splitlines() if line.strip())

