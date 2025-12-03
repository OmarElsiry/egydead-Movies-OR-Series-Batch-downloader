import requests
import re
import sys
import time
from urllib.parse import quote, unquote, urlparse

# ... (imports)

class EgyDeadDL:
    def __init__(self):
        self.base_url = "https://egydead.skin"
        self.search_url = f"{self.base_url}/?s="
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def search(self, query):
        print(f"Searching for: {query}")
        encoded_query = quote(query)
        url = f"{self.search_url}{encoded_query}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error during search: {e}")
            return []

        results = []
        movie_items = re.findall(r'<li class="movieItem">(.*?)</li>', response.text, re.DOTALL)
        
        for item in movie_items:
            link_match = re.search(r'<a href="(.*?)"', item)
            title_match = re.search(r'<h1 class="BottomTitle">(.*?)</h1>', item)
            
            if link_match and title_match:
                results.append({
                    'url': link_match.group(1),
                    'title': title_match.group(1)
                })
                
        return results

    def process_url(self, url, fetch_all=False):
        print(f"Processing URL: {url}")
        
        if '/serie/' in url:
            self.handle_series(url)
        elif '/season/' in url:
            self.handle_season(url, fetch_all=fetch_all)
        else:
            # Assume it's a movie or episode (downloadable)
            self.handle_download_page(url)

    def handle_series(self, url):
        print("Detected Series. Fetching Seasons...")
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error: {e}")
            return

        links = re.findall(r'href="([^"]*/season/[^"]*)"', response.text)
        seen = set()
        unique_links = []
        for l in links:
            if l not in seen:
                seen.add(l)
                unique_links.append(l)
        
        if not unique_links:
            print("No seasons found.")
            return

        print(f"Found {len(unique_links)} Seasons:")
        for i, link in enumerate(unique_links):
            name = unquote(link.split('/')[-2]).replace('-', ' ')
            print(f"{i+1}. {name} : {link}")

    def handle_season(self, url, fetch_all=False):
        print("Detected Season. Fetching Episodes...")
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error: {e}")
            return

        links = re.findall(r'href="([^"]*/episode/[^"]*)"', response.text)
        seen = set()
        unique_links = []
        for l in links:
            if l not in seen:
                seen.add(l)
                unique_links.append(l)
        
        if not unique_links:
            print("No episodes found.")
            return

        print(f"Found {len(unique_links)} Episodes:")
        if fetch_all:
            for i, link in enumerate(unique_links):
                name = unquote(link.split('/')[-2]).replace('-', ' ')
                print(f"\n[{i+1}/{len(unique_links)}] Processing {name} : {link}")
                self.handle_download_page(link)
        else:
            for i, link in enumerate(unique_links):
                name = unquote(link.split('/')[-2]).replace('-', ' ')
                print(f"{i+1}. {name} : {link}")

    def handle_download_page(self, url):
        links = self.get_download_links(url)
        if not links:
            print("No download links found.")
        else:
            print(f"Found {len(links)} download links:")
            for i, link in enumerate(links):
                server = link['server']
                dl_url = link['url']
                resolved_url = None
                
                # Attempt to resolve DoodStream using requests (optional, can be kept or removed)
                if 'dood' in dl_url or 'dsvplay' in dl_url:
                     resolved_url = self.resolve_doodstream(dl_url)
                
                if resolved_url:
                    print(f"{i + 1}. Server: {server} | Quality: {link['quality']} | URL: {dl_url}")
                    print(f"    -> DIRECT DOWNLOAD: {resolved_url}")
                else:
                    print(f"{i + 1}. Server: {server} | Quality: {link['quality']} | URL: {dl_url}")

    def resolve_doodstream(self, url):
        try:
            session = requests.Session()
            session.headers.update(self.headers)
            
            # Step 1: Get the embed/landing page
            response = session.get(url)
            response.raise_for_status()
            
            # Step 2: Find the "High quality" or "Download" link (looking for /download/ path)
            download_page_match = re.search(r'href="([^"]*/download/[^"]*)"', response.text)
            if not download_page_match:
                return None
            
            download_page_url = download_page_match.group(1)
            if not download_page_url.startswith('http'):
                if download_page_url.startswith('//'):
                    download_page_url = 'https:' + download_page_url
                elif download_page_url.startswith('/'):
                    parsed_url = urlparse(url)
                    download_page_url = f"{parsed_url.scheme}://{parsed_url.netloc}{download_page_url}"

            # Step 3: Get the final download page with Referer
            session.headers.update({'Referer': url})
            response = session.get(download_page_url)
            response.raise_for_status()
            
            # Step 3.5: Check for form submission (Security error / intermediate page)
            if '<Form name="F1"' in response.text:
                try:
                    op = re.search(r'name="op" value="(.*?)"', response.text).group(1)
                    id_val = re.search(r'name="id" value="(.*?)"', response.text).group(1)
                    mode = re.search(r'name="mode" value="(.*?)"', response.text).group(1)
                    hash_val = re.search(r'name="hash" value="(.*?)"', response.text).group(1)
                    
                    time.sleep(2) # Wait a bit to mimic human
                    
                    post_data = {
                        'op': op,
                        'id': id_val,
                        'mode': mode,
                        'hash': hash_val
                    }
                    
                    session.headers.update({'Referer': download_page_url})
                    response = session.post(download_page_url, data=post_data)
                    response.raise_for_status()
                except AttributeError:
                    pass
            
            # Step 4: Extract the final file link
            final_link_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>Download file</a>', response.text)
            if final_link_match:
                return final_link_match.group(1)
            
            token_match = re.search(r'href="([^"]+token=[^"]+expiry=[^"]+)"', response.text)
            if token_match:
                return token_match.group(1)

        except Exception as e:
            # print(f"Error resolving DoodStream: {e}")
            pass
        return None

    def get_download_links(self, movie_url):
        try:
            response = requests.post(movie_url, data={'View': '1'}, headers=self.headers)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching movie page: {e}")
            return []

        links = []
        pattern = r'<span class="ser-name">(.*?)</span>.*?<em>(.*?)</em>.*?href="(.*?)"'
        matches = re.findall(pattern, response.text, re.DOTALL)
        
        for match in matches:
            server_name = match[0].strip()
            quality = match[1].strip()
            url = match[2].strip()
            
            if url and not url.startswith('javascript'):
                links.append({
                    'server': server_name,
                    'quality': quality,
                    'url': url
                })
                
        return links

def main():
    if len(sys.argv) < 2:
        print("Usage: python egydead_dl.py <search_query_OR_url> [selection_index] [--all]")
        sys.exit(1)

    fetch_all = '--all' in sys.argv
    if fetch_all:
        sys.argv.remove('--all')

    if len(sys.argv) < 2:
         print("Usage: python egydead_dl.py <search_query_OR_url> [selection_index] [--all]")
         sys.exit(1)

    input_arg = sys.argv[1]
    selection_index = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else None

    dl = EgyDeadDL()

    if input_arg.startswith('http'):
        dl.process_url(input_arg, fetch_all=fetch_all)
    else:
        results = dl.search(input_arg)
        
        if not results:
            print("No results found.")
            sys.exit(0)
            
        print(f"\nFound {len(results)} results:")
        for i, res in enumerate(results):
            print(f"{i + 1}. {res['title']}")
            
        if selection_index is None:
            try:
                choice = int(input("\nEnter the number of the movie to download: ")) - 1
            except ValueError:
                print("Invalid input. Please enter a number.")
                sys.exit(1)
        else:
            choice = selection_index

        if 0 <= choice < len(results):
            selected_movie = results[choice]
            print(f"\nSelected: {selected_movie['title']}")
            dl.process_url(selected_movie['url'], fetch_all=fetch_all)
        else:
            print("Invalid selection.")

if __name__ == "__main__":
    main()
