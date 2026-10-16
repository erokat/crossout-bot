# -*- coding: utf-8 -*-
# SKILL_NAME: web_search_skill
# DESCRIPTION: Умный поиск информации, новостей, фактов и ответов на вопросы в интернете
# TRIGGERS: найди в интернете, поиск в интернете, погугли, найди в сети, что известно о, поищи в интернете, поиск информации, найди информацию, загугли, в интернете, найти в интернете, поищи в сети, поиск в сети, информацию о, информацию про
# REQUIREMENTS: 

import os
import sys
import re
import json
import html
import hashlib
import urllib.request
import urllib.parse

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")

def clean_query(raw_query):
    if not raw_query:
        return ""
    q = raw_query.strip()
    # Strip bot address prefixes
    q = re.sub(r"^(?:[!/]?бот[,\s]*|ботик[,\s]*|ботяра[,\s]*|bot[,\s]*)", "", q, flags=re.IGNORECASE).strip()
    
    # Strip joke parenthetical remarks like (о Ярике), (про Ярика), etc.
    q = re.sub(r"\s*\([^)]*(?:ярик|миш|прикол|мем)[^)]*\)\s*", " ", q, flags=re.IGNORECASE).strip()
    
    patterns = [
        r"^найди(?:-ка)?\s+(?:всё\s+)?в\s+(?:интернете|сети)\s*",
        r"^поищи(?:-ка)?\s+(?:всё\s+)?в\s+(?:интернете|сети)\s*",
        r"^поиск\s+(?:в\s+(?:интернете|сети)|информации)\s*",
        r"^найди\s+(?:всю\s+)?информацию\s*",
        r"^поищи\s+(?:всю\s+)?информацию\s*",
        r"^(?:информаци[юяи]|инфу|справку|данные|статью|новости|факты)\s*",
        r"^(?:что\s+известно|расскажи|погугли|загугли|найди|поищи)\s*",
        r"^(?:про|о|об|насчёт)\s*",
        r"\s+в\s+(?:интернете|сети)$",
    ]
    for _ in range(4):
        changed = False
        for pat in patterns:
            new_q = re.sub(pat, "", q, flags=re.IGNORECASE).strip()
            if new_q != q and new_q:
                q = new_q
                changed = True
        if not changed:
            break
            
    # Strip quotes if surrounded
    if (q.startswith('"') and q.endswith('"')) or (q.startswith('«') and q.endswith('»')):
        q = q[1:-1].strip()
        
    return q or raw_query.strip()

def search_wikipedia(query):
    """Ищет краткую энциклопедическую выжимку и фото в Википедии (REST API / Search API)."""
    if not query:
        return None
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 1. Try direct page summary
    try:
        url = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            extract = data.get("extract")
            title = data.get("title")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
            img_url = data.get("originalimage", {}).get("source") or data.get("thumbnail", {}).get("source")
            if extract and len(extract) > 30:
                return {
                    "title": title,
                    "extract": extract.strip(),
                    "url": page_url or f"https://ru.wikipedia.org/wiki/{urllib.parse.quote(title)}",
                    "image_url": img_url
                }
    except Exception:
        pass

    # 2. Try opensearch / search API to find exact title
    try:
        search_url = (
            f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&format=json&utf8=1&srlimit=1"
        )
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            s_data = json.loads(resp.read().decode("utf-8"))
            results = s_data.get("query", {}).get("search", [])
            if results:
                top_title = results[0].get("title")
                snippet = results[0].get("snippet", "")
                snippet_clean = html.unescape(re.sub(r"<[^>]+>", "", snippet)).strip()
                
                # Fetch full extract and thumbnail for top match
                url_sum = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(top_title)}"
                req_sum = urllib.request.Request(url_sum, headers=headers)
                try:
                    with urllib.request.urlopen(req_sum, timeout=5) as r_sum:
                        d_sum = json.loads(r_sum.read().decode("utf-8"))
                        ext = d_sum.get("extract")
                        top_img = d_sum.get("originalimage", {}).get("source") or d_sum.get("thumbnail", {}).get("source")
                        if ext:
                            return {
                                "title": top_title,
                                "extract": ext.strip(),
                                "url": f"https://ru.wikipedia.org/wiki/{urllib.parse.quote(top_title)}",
                                "image_url": top_img
                            }
                except Exception:
                    pass
                
                if snippet_clean:
                    return {
                        "title": top_title,
                        "extract": snippet_clean,
                        "url": f"https://ru.wikipedia.org/wiki/{urllib.parse.quote(top_title)}",
                        "image_url": None
                    }
    except Exception:
        pass

    return None

def search_duckduckgo(query, max_results=4):
    """Выполняет поиск в сети через DuckDuckGo Lite без внешних зависимостей."""
    if not query:
        return []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    url = "https://lite.duckduckgo.com/lite/"
    post_data = urllib.parse.urlencode({"q": query, "kl": "ru-ru"}).encode("utf-8")
    
    results = []
    try:
        req = urllib.request.Request(url, data=post_data, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            
        links = re.findall(r"<a rel=['\"]nofollow['\"] href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>", content, re.DOTALL)
        snippets = re.findall(r"<td class=['\"]result-snippet['\"]>(.*?)</td>", content, re.DOTALL)
        
        for i in range(min(len(links), max_results)):
            raw_url = links[i][0]
            # Unwrap DuckDuckGo redirect if present
            if "duckduckgo.com/l/?uddg=" in raw_url:
                m = re.search(r"uddg=([^&]+)", raw_url)
                if m:
                    raw_url = urllib.parse.unquote(m.group(1))
            
            raw_title = links[i][1]
            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            
            snip = ""
            if i < len(snippets):
                snip = html.unescape(re.sub(r"<[^>]+>", "", snippets[i])).strip()
            
            # Avoid empty or ad results
            if raw_url.startswith("http") and title:
                results.append({
                    "title": title,
                    "url": raw_url,
                    "snippet": snip
                })
    except Exception as e:
        pass
    
    return results

def download_topic_image(image_url, query_name):
    """Скачивает иллюстративное фото темы в ./media/ для наглядности."""
    if not image_url:
        return None
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        q_hash = hashlib.md5(query_name.encode("utf-8")).hexdigest()[:8]
        ext = ".png" if ".png" in image_url.lower() else ".jpg"
        out_path = os.path.join(MEDIA_DIR, f"search_{q_hash}{ext}")
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=8) as resp, open(out_path, "wb") as f:
            f.write(resp.read())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path
    except Exception:
        pass
    return None

def web_search(query_text=""):
    raw_input = query_text or os.environ.get("TASK_TEXT", "") or (sys.argv[1] if len(sys.argv) > 1 else "")
    sender_name = os.environ.get("SENDER_NAME", "Миша")
    clean_q = clean_query(raw_input)
    
    if not clean_q:
        return f"🔍 {sender_name}, укажи, что именно нужно найти в интернете!"
    
    # Run searches
    wiki_info = search_wikipedia(clean_q)
    web_results = search_duckduckgo(clean_q, max_results=4)
    
    if not wiki_info and not web_results:
        # Fallback search with broader terms
        web_results = search_duckduckgo(raw_input, max_results=4)
    
    if not wiki_info and not web_results:
        return f"🔍 {sender_name}, по запросу «{clean_q}» ничего не удалось найти в сети. Попробуй переформулировать запрос!"
    
    # Try downloading topic image if available from Wikipedia
    local_image = None
    if wiki_info and wiki_info.get("image_url"):
        local_image = download_topic_image(wiki_info["image_url"], clean_q)
    
    lines = [f"🔍 **Результаты поиска в интернете по запросу:** «{clean_q}»\n"]
    
    # 1. Wiki card if available
    if wiki_info:
        lines.append(f"📖 **Справка ({wiki_info['title']}):**")
        lines.append(f"{wiki_info['extract']}\n")
    
    # 2. Web links
    if web_results:
        lines.append("🌐 **Полезные источники и ссылки:**")
        for idx, res in enumerate(web_results, 1):
            title = res["title"]
            url = res["url"]
            snippet = res["snippet"]
            
            # Truncate snippet if too long
            if len(snippet) > 180:
                snippet = snippet[:177] + "..."
            
            lines.append(f"{idx}. [{title}]({url})")
            if snippet:
                lines.append(f"   {snippet}")
        lines.append("")
        
    lines.append(f"✨ Найдено в сети для {sender_name}")
    report_text = "\n".join(lines)

    # If an image was downloaded, output path first so dynamic engine pairs photo with text
    if local_image and os.path.exists(local_image):
        return f"{local_image}\n{report_text}"
    return report_text

if __name__ == "__main__":
    task_input = " ".join(sys.argv[1:]) or os.environ.get("TASK_TEXT", "")
    print(web_search(task_input))
