from mitmproxy import http
import os
import gzip
from io import BytesIO
import re

CACHE_DIR = "./cache"


def url_to_filename(url: str) -> str:
    url = url.replace("http://www.sofascore.com/", "http://localhost:8080/")
    # Replace characters that are not safe in filenames
    safe_filename = re.sub(r'[<>:"/\\|?*\s]', '-', url)
    return os.path.join(CACHE_DIR, f"{safe_filename}.bin").replace("\\", "/")


def load_from_cache(filename: str) -> bytes:
    with open(filename, "rb") as f:
        return f.read()


def save_to_cache(filename: str, content: bytes):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(filename, "wb") as f:
        f.write(content)
        f.close()


class CacheResponses:
    def request(self, flow: http.HTTPFlow):
        url = flow.request.url
        filename = url_to_filename(url)

        if os.path.exists(filename):
            print(f"[CACHE HIT] Serving cached response for: {url}")
            cached_content = load_from_cache(filename)
            flow.response = http.Response.make(
                200,  # (optional) HTTP status code
                cached_content,
                {"Content-Type": "application/json"}  # adjust headers as needed
            )

    def response(self, flow: http.HTTPFlow):
        url = flow.request.url
        filename = url_to_filename(url)

        # Only cache successful (status 200) responses
        if flow.response.status_code != 200:
            print(f"[SKIP CACHE] Not caching response for {url} (status: {flow.response.status_code})")
            return

        content = flow.response.raw_content
        encoding = flow.response.headers.get("Content-Encoding", "")

        if "gzip" in encoding.lower():
            try:
                with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                    content = gz.read()
                # Update headers for decompressed content
                flow.response.headers["Content-Encoding"] = ""
                flow.response.headers["Content-Length"] = str(len(content))
                flow.response.content = content
            except Exception as e:
                print(f"[!] Gzip decompression failed for {url}: {e}")
                # fallback: leave content as is

        save_to_cache(filename, content)


addons = [CacheResponses()]

# Example usage for manual testing
if __name__ == "__main__":
    url = "http://localhost:8080/api/v1/search/all?q=laliga&page=0"
    print(url_to_filename(url))
